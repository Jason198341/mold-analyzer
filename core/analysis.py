"""구배각(Draft Angle), 언더컷, 파팅라인 분석 모듈.

각 Face에 대해:
- 구배각 계산 (금형 열림 방향 기준)
- 언더컷 여부 판별
- 파팅라인 후보 Edge 추출
"""

import math
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp_Face
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.gp import gp_Dir, gp_Vec, gp_Pnt
from OCP.GeomAbs import (
    GeomAbs_Plane,
    GeomAbs_Cylinder,
    GeomAbs_Cone,
    GeomAbs_Sphere,
    GeomAbs_Torus,
    GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface,
)


# ─── 면 유형 이름 매핑 ───────────────────────────────

SURFACE_TYPE_NAMES = {
    GeomAbs_Plane: "평면 (Plane)",
    GeomAbs_Cylinder: "원통면 (Cylinder)",
    GeomAbs_Cone: "원추면 (Cone)",
    GeomAbs_Sphere: "구면 (Sphere)",
    GeomAbs_Torus: "토러스 (Torus)",
    GeomAbs_BSplineSurface: "B-Spline 곡면",
    GeomAbs_BezierSurface: "Bezier 곡면",
}


def _surface_type_name(surface_type) -> str:
    return SURFACE_TYPE_NAMES.get(surface_type, "기타 곡면")


# ─── 구배각 분석 ─────────────────────────────────────

def analyze_face(face, opening_dir: gp_Dir, n_samples: int = 5) -> dict:
    """단일 Face의 구배각, 면 유형, 면적을 분석합니다.

    구배각 = arcsin(|법선벡터 · 열림방향|)
    - 0° = 수직 벽 (구배 없음, 금형에 걸림)
    - 90° = 수평면 (열림방향과 평행)
    """
    adaptor = BRepAdaptor_Surface(face)
    surface_type = adaptor.GetType()

    # 면적 계산
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    area = props.Mass()
    center = props.CentreOfMass()

    # UV 범위에서 법선 샘플링
    u_min, u_max = adaptor.FirstUParameter(), adaptor.LastUParameter()
    v_min, v_max = adaptor.FirstVParameter(), adaptor.LastVParameter()

    face_props = BRepGProp_Face(face)
    draft_angles = []
    normals = []
    raw_dots = []  # 부호 포함 (언더컷 판별용)

    for i in range(n_samples):
        for j in range(n_samples):
            u = u_min + (u_max - u_min) * (i + 0.5) / n_samples
            v = v_min + (v_max - v_min) * (j + 0.5) / n_samples

            pnt = gp_Pnt()
            normal = gp_Vec()
            face_props.Normal(u, v, pnt, normal)

            if normal.Magnitude() < 1e-10:
                continue

            normal.Normalize()
            normals.append((normal.X(), normal.Y(), normal.Z()))

            # 법선 · 열림방향 (부호 유지)
            dot = (normal.X() * opening_dir.X() +
                   normal.Y() * opening_dir.Y() +
                   normal.Z() * opening_dir.Z())
            raw_dots.append(dot)

            # 구배각 = arcsin(|dot|)
            draft_deg = math.degrees(math.asin(min(abs(dot), 1.0)))
            draft_angles.append(draft_deg)

    if not draft_angles:
        return {
            "surface_type": _surface_type_name(surface_type),
            "area": area,
            "min_draft": 0.0,
            "max_draft": 0.0,
            "avg_draft": 0.0,
            "draft_category": "unknown",
            "is_undercut": False,
            "center": (center.X(), center.Y(), center.Z()),
            "normals": [],
        }

    min_draft = min(draft_angles)
    max_draft = max(draft_angles)
    avg_draft = sum(draft_angles) / len(draft_angles)

    # 카테고리 분류
    if avg_draft > 85:
        category = "horizontal"      # 수평면 (상/하면)
    elif min_draft >= 3:
        category = "good"            # 충분한 구배 (3°+)
    elif min_draft >= 1:
        category = "marginal"        # 경계 (1~3°)
    elif min_draft >= 0.1:
        category = "insufficient"    # 불충분 (<1°)
    else:
        category = "zero"            # 구배 없음 (0°)

    # 언더컷 판별: 법선 방향이 혼재하면 의심
    has_positive = any(d > 0.05 for d in raw_dots)
    has_negative = any(d < -0.05 for d in raw_dots)
    is_undercut = has_positive and has_negative and avg_draft < 45

    return {
        "surface_type": _surface_type_name(surface_type),
        "area": area,
        "min_draft": min_draft,
        "max_draft": max_draft,
        "avg_draft": avg_draft,
        "draft_category": category,
        "is_undercut": is_undercut,
        "center": (center.X(), center.Y(), center.Z()),
        "normals": normals,
    }


def analyze_all_faces(faces: list, opening_dir: gp_Dir = None) -> list:
    """모든 Face를 분석합니다."""
    if opening_dir is None:
        opening_dir = gp_Dir(0, 0, 1)

    results = []
    for i, face in enumerate(faces):
        result = analyze_face(face, opening_dir)
        result["face_id"] = i
        results.append(result)
    return results


# ─── 파팅라인 추정 ──────────────────────────────────

def estimate_parting_line(shape, faces: list, face_results: list,
                          opening_dir: gp_Dir = None) -> dict:
    """파팅라인을 추정합니다."""
    if opening_dir is None:
        opening_dir = gp_Dir(0, 0, 1)

    from .reader import get_bounding_box
    bbox = get_bounding_box(shape)

    z_mid = (bbox["zmin"] + bbox["zmax"]) / 2

    upper_faces = []
    lower_faces = []
    vertical_faces = []

    for result in face_results:
        if not result["normals"]:
            continue

        avg_nz = sum(n[2] for n in result["normals"]) / len(result["normals"])

        if avg_nz > 0.1:
            upper_faces.append(result["face_id"])
        elif avg_nz < -0.1:
            lower_faces.append(result["face_id"])
        else:
            vertical_faces.append(result["face_id"])

    # 가장 넓은 단면의 Z 높이 추정
    z_centers = [r["center"][2] for r in face_results if r["center"]]
    if z_centers:
        n_bins = 20
        z_range = bbox["dz"] if bbox["dz"] > 0 else 1
        bin_size = z_range / n_bins
        bins = [0] * n_bins
        for z in z_centers:
            idx = int((z - bbox["zmin"]) / bin_size)
            idx = min(idx, n_bins - 1)
            bins[idx] += 1

        max_bin = bins.index(max(bins))
        estimated_z = bbox["zmin"] + (max_bin + 0.5) * bin_size
    else:
        estimated_z = z_mid

    return {
        "parting_z": estimated_z,
        "z_mid": z_mid,
        "upper_face_count": len(upper_faces),
        "lower_face_count": len(lower_faces),
        "vertical_face_count": len(vertical_faces),
        "vertical_face_ids": vertical_faces,
        "bbox": bbox,
    }


# ─── 언더컷 상세 검출 ───────────────────────────────

def detect_undercuts(face_results: list, parting_z: float,
                     opening_dir: gp_Dir = None) -> list:
    """파팅라인 기준으로 언더컷을 상세 검출합니다."""
    undercuts = []

    for result in face_results:
        if not result["normals"]:
            continue

        avg_draft = result["avg_draft"]
        if avg_draft > 80:
            continue

        center_z = result["center"][2]
        avg_nz = sum(n[2] for n in result["normals"]) / len(result["normals"])

        is_undercut = False
        reason = ""

        if center_z > parting_z and avg_nz < -0.1 and avg_draft < 45:
            is_undercut = True
            reason = "Cavity 측 언더컷 (법선이 아래를 향함)"

        if center_z < parting_z and avg_nz > 0.1 and avg_draft < 45:
            is_undercut = True
            reason = "Core 측 언더컷 (법선이 위를 향함)"

        if avg_draft < 0.5 and not is_undercut:
            is_undercut = True
            reason = f"구배 부족 (평균 {avg_draft:.1f}°, 이형 불가 위험)"

        if is_undercut or result.get("is_undercut"):
            undercuts.append({
                "face_id": result["face_id"],
                "reason": reason or "법선 방향 혼재",
                "center": result["center"],
                "avg_draft": avg_draft,
                "surface_type": result["surface_type"],
                "area": result["area"],
            })

    return undercuts


# ─── 요약 통계 ──────────────────────────────────────

def summarize(face_results: list) -> dict:
    """분석 결과 요약 통계를 생성합니다."""
    total = len(face_results)
    categories = {}
    for r in face_results:
        cat = r["draft_category"]
        categories[cat] = categories.get(cat, 0) + 1

    all_drafts = [r["avg_draft"] for r in face_results if r["normals"]]
    surface_types = {}
    for r in face_results:
        st = r["surface_type"]
        surface_types[st] = surface_types.get(st, 0) + 1

    total_area = sum(r["area"] for r in face_results)

    return {
        "total_faces": total,
        "categories": categories,
        "surface_types": surface_types,
        "total_area": total_area,
        "min_draft_overall": min(all_drafts) if all_drafts else 0,
        "max_draft_overall": max(all_drafts) if all_drafts else 0,
        "avg_draft_overall": (sum(all_drafts) / len(all_drafts)) if all_drafts else 0,
    }
