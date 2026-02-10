"""구배각(Draft Angle), 언더컷, 파팅라인 분석 모듈.

각 Face에 대해:
- 구배각 계산 (금형 열림 방향 기준)
- 언더컷 여부 판별
- 파팅라인 후보 Edge 추출
"""

import math
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp_Face
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.gp import gp_Dir, gp_Vec, gp_Pnt, gp_Lin
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
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

def analyze_face(face, opening_dir: gp_Dir, n_samples: int = 0) -> dict:
    """단일 Face의 구배각, 면 유형, 면적을 분석합니다.

    n_samples=0이면 면 유형에 따라 적응적 샘플링:
    - 평면(Plane): 1×1 (법선 일정)
    - 원통/원추(Cylinder/Cone): 5×5
    - B-Spline/Bezier 자유곡면: 10×10 (정밀 분석)
    - 기타: 5×5
    """
    adaptor = BRepAdaptor_Surface(face)
    surface_type = adaptor.GetType()

    # 적응적 샘플링: 면 유형별 최적 샘플 수 결정
    if n_samples <= 0:
        if surface_type == GeomAbs_Plane:
            n_samples = 1
        elif surface_type in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface):
            n_samples = 10
        else:
            n_samples = 5

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

def _silhouette_parting_line(shape, faces, opening_dir):
    """실루엣 엣지 기반 파팅라인 추출.

    각 엣지의 양쪽 면 법선이 열림 방향 기준 반대 부호면 실루엣 엣지.
    이 엣지들이 파팅라인 후보입니다.

    Returns:
        (silhouette_points, silhouette_z) or (None, None) if fails
    """
    try:
        # 엣지 → 인접 면 매핑
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

        # 면 인덱스 매핑 (OCC Face → face_id)
        face_idx_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_idx_map)

        silhouette_points = []

        for i in range(1, edge_face_map.Extent() + 1):
            edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
            face_list = edge_face_map.FindFromIndex(i)

            if face_list.Extent() != 2:
                continue

            # 양쪽 면의 법선 dot product 부호 확인
            it = face_list.cbegin()
            face1 = TopoDS.Face_s(it.Value())
            it.Next()
            face2 = TopoDS.Face_s(it.Value())

            fp1 = BRepGProp_Face(face1)
            fp2 = BRepGProp_Face(face2)

            # 엣지 중점에서 양쪽 면의 법선 평가
            curve = BRepAdaptor_Curve(edge)
            u_mid = (curve.FirstParameter() + curve.LastParameter()) / 2
            mid_pnt = curve.Value(u_mid)

            # 면1의 법선 (면 위 가장 가까운 UV에서)
            adaptor1 = BRepAdaptor_Surface(face1)
            adaptor2 = BRepAdaptor_Surface(face2)

            u1 = (adaptor1.FirstUParameter() + adaptor1.LastUParameter()) / 2
            v1 = (adaptor1.FirstVParameter() + adaptor1.LastVParameter()) / 2
            u2 = (adaptor2.FirstUParameter() + adaptor2.LastUParameter()) / 2
            v2 = (adaptor2.FirstVParameter() + adaptor2.LastVParameter()) / 2

            n1_pnt, n1_vec = gp_Pnt(), gp_Vec()
            n2_pnt, n2_vec = gp_Pnt(), gp_Vec()
            fp1.Normal(u1, v1, n1_pnt, n1_vec)
            fp2.Normal(u2, v2, n2_pnt, n2_vec)

            if n1_vec.Magnitude() < 1e-10 or n2_vec.Magnitude() < 1e-10:
                continue

            n1_vec.Normalize()
            n2_vec.Normalize()

            dot1 = (n1_vec.X() * opening_dir.X() +
                    n1_vec.Y() * opening_dir.Y() +
                    n1_vec.Z() * opening_dir.Z())
            dot2 = (n2_vec.X() * opening_dir.X() +
                    n2_vec.Y() * opening_dir.Y() +
                    n2_vec.Z() * opening_dir.Z())

            # 한쪽은 양, 한쪽은 음 → 실루엣 엣지
            if dot1 * dot2 < -0.01:
                # 엣지 위의 점들 추출
                n_pts = 5
                for k in range(n_pts + 1):
                    u = curve.FirstParameter() + (curve.LastParameter() - curve.FirstParameter()) * k / n_pts
                    pnt = curve.Value(u)
                    silhouette_points.append([pnt.X(), pnt.Y(), pnt.Z()])

        if len(silhouette_points) >= 3:
            # 실루엣 포인트의 평균 Z → 파팅라인 Z
            avg_z = sum(p[2] for p in silhouette_points) / len(silhouette_points)
            return silhouette_points, avg_z

    except Exception:
        pass

    return None, None


def estimate_parting_line(shape, faces: list, face_results: list,
                          opening_dir: gp_Dir = None) -> dict:
    """파팅라인을 추정합니다.

    1차: 실루엣 엣지 방식 (B-Rep 토폴로지 기반)
    2차: Z 히스토그램 방식 (fallback)
    """
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

    # ── 1차: 실루엣 엣지 방식 ──
    silhouette_points, silhouette_z = _silhouette_parting_line(shape, faces, opening_dir)
    method = "silhouette"

    if silhouette_z is not None:
        estimated_z = silhouette_z
    else:
        # ── 2차: Z 히스토그램 방식 (fallback) ──
        method = "histogram"
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
        "silhouette_points": silhouette_points or [],
        "parting_method": method,
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


# ─── 벽 두께 분석 (레이캐스팅) ───────────────────────

def analyze_wall_thickness(shape, faces: list, n_samples: int = 3) -> dict:
    """레이캐스팅으로 벽 두께를 분석합니다.

    각 면의 표면 샘플 포인트에서 법선 반대 방향(내부)으로 레이를 발사하여
    반대편 면까지의 거리를 측정합니다.

    Returns:
        dict with face_thicknesses, overall stats, warnings, histogram
    """
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(shape, 1e-6)

    face_thicknesses = []
    all_thicknesses = []
    OFFSET = 0.02  # 자기면 교차 회피 오프셋 (mm)

    for face_idx, face in enumerate(faces):
        adaptor = BRepAdaptor_Surface(face)
        u_min, u_max = adaptor.FirstUParameter(), adaptor.LastUParameter()
        v_min, v_max = adaptor.FirstVParameter(), adaptor.LastVParameter()

        face_props = BRepGProp_Face(face)
        thicknesses = []

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

                # 법선 반대 방향 (내부)으로 레이 발사
                ray_dir = gp_Dir(-normal.X(), -normal.Y(), -normal.Z())
                ray_origin = gp_Pnt(
                    pnt.X() + ray_dir.X() * OFFSET,
                    pnt.Y() + ray_dir.Y() * OFFSET,
                    pnt.Z() + ray_dir.Z() * OFFSET,
                )
                ray = gp_Lin(ray_origin, ray_dir)

                try:
                    intersector.Perform(ray, 0, 500)  # 최대 500mm 탐색

                    if intersector.NbPnt() > 0:
                        min_dist = float('inf')
                        for k in range(1, intersector.NbPnt() + 1):
                            dist = intersector.WParameter(k) + OFFSET
                            if dist > OFFSET * 3 and dist < min_dist:
                                min_dist = dist

                        if min_dist < float('inf'):
                            thicknesses.append(min_dist)
                            all_thicknesses.append(min_dist)
                except Exception:
                    continue

        if thicknesses:
            face_thicknesses.append({
                "face_id": face_idx,
                "min_thickness": min(thicknesses),
                "max_thickness": max(thicknesses),
                "avg_thickness": sum(thicknesses) / len(thicknesses),
                "samples": len(thicknesses),
            })
        else:
            face_thicknesses.append({
                "face_id": face_idx,
                "min_thickness": 0,
                "max_thickness": 0,
                "avg_thickness": 0,
                "samples": 0,
            })

    # 전체 통계
    warnings = []
    if all_thicknesses:
        min_t = min(all_thicknesses)
        max_t = max(all_thicknesses)
        avg_t = sum(all_thicknesses) / len(all_thicknesses)

        if min_t < 0.8:
            warnings.append(f"최소 벽 두께 {min_t:.2f}mm → 충전불량 위험 (<0.8mm)")
        if max_t > 4.0:
            warnings.append(f"최대 벽 두께 {max_t:.2f}mm → 싱크마크 위험 (>4mm)")
        if min_t > 0.01 and max_t / min_t > 2:
            warnings.append(f"두께비 {max_t / min_t:.1f}:1 → 수축편차 위험 (>2:1)")
    else:
        min_t = max_t = avg_t = 0

    # 히스토그램 (10구간)
    histogram = None
    if all_thicknesses and max_t > min_t:
        n_bins = 10
        bin_range = max_t - min_t
        bins = [0] * n_bins
        for t in all_thicknesses:
            idx = min(int((t - min_t) / bin_range * (n_bins - 0.01)), n_bins - 1)
            bins[idx] += 1
        histogram = {
            "bins": bins,
            "min": min_t,
            "max": max_t,
            "bin_size": bin_range / n_bins,
        }

    return {
        "face_thicknesses": face_thicknesses,
        "min_thickness": min_t,
        "max_thickness": max_t,
        "avg_thickness": avg_t,
        "thickness_ratio": max_t / max(min_t, 0.01),
        "warnings": warnings,
        "histogram": histogram,
        "total_samples": len(all_thicknesses),
    }


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

    # 면적 가중 평균 드래프트각
    weighted_sum = sum(r["avg_draft"] * r["area"] for r in face_results if r["normals"])
    weighted_area = sum(r["area"] for r in face_results if r["normals"])
    weighted_avg = weighted_sum / weighted_area if weighted_area > 0 else 0

    return {
        "total_faces": total,
        "categories": categories,
        "surface_types": surface_types,
        "total_area": total_area,
        "min_draft_overall": min(all_drafts) if all_drafts else 0,
        "max_draft_overall": max(all_drafts) if all_drafts else 0,
        "avg_draft_overall": (sum(all_drafts) / len(all_drafts)) if all_drafts else 0,
        "weighted_avg_draft": weighted_avg,
    }
