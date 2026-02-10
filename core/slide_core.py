"""슬라이드 코어 / 경사 코어 분석 및 제안 모듈.

언더컷 영역을 분석하여:
1. 슬라이드 코어가 필요한 부위 그룹핑
2. 슬라이드 방향 (이동 방향) 결정
3. 이동 거리 (stroke) 계산
4. 슬라이드 vs 경사코어 판단
5. 금형 레이아웃 제안
"""

import math
import numpy as np
from OCP.gp import gp_Dir


# ─── 슬라이드 방향 정규화 ───────────────────────────

# 8방향으로 정규화 (실제 금형은 직교 방향이 대부분)
CANONICAL_DIRECTIONS = {
    "+X":  np.array([ 1,  0, 0]),
    "-X":  np.array([-1,  0, 0]),
    "+Y":  np.array([ 0,  1, 0]),
    "-Y":  np.array([ 0, -1, 0]),
    "+X+Y": np.array([ 1,  1, 0]) / math.sqrt(2),
    "+X-Y": np.array([ 1, -1, 0]) / math.sqrt(2),
    "-X+Y": np.array([-1,  1, 0]) / math.sqrt(2),
    "-X-Y": np.array([-1, -1, 0]) / math.sqrt(2),
}


def _nearest_canonical(direction: np.ndarray) -> tuple:
    """주어진 방향을 가장 가까운 정규 방향으로 매핑합니다."""
    best_name = "+X"
    best_dot = -999
    for name, canonical in CANONICAL_DIRECTIONS.items():
        dot = np.dot(direction, canonical)
        if dot > best_dot:
            best_dot = dot
            best_name = name
    return best_name, CANONICAL_DIRECTIONS[best_name]


def _compute_slide_direction(normals: list, opening_dir_z: bool = True) -> np.ndarray:
    """언더컷 면의 법선들로부터 슬라이드 방향을 계산합니다.

    슬라이드는 언더컷 법선의 수평 성분 방향으로 이동해야 합니다.
    """
    if not normals:
        return np.array([1, 0, 0])

    # 법선들의 평균
    avg_normal = np.mean(normals, axis=0)

    # 열림 방향(Z) 성분 제거 → 수평면에 투영
    if opening_dir_z:
        avg_normal[2] = 0

    norm = np.linalg.norm(avg_normal)
    if norm < 1e-10:
        return np.array([1, 0, 0])

    return avg_normal / norm


# ─── 언더컷 그룹핑 ─────────────────────────────────

def group_undercuts(undercuts: list, face_results: list,
                    distance_threshold: float = 20.0,
                    angle_threshold: float = 45.0) -> list:
    """가까이 있고 비슷한 방향의 언더컷들을 그룹핑합니다.

    같은 슬라이드 코어로 처리할 수 있는 언더컷 면들을 묶습니다.

    Args:
        undercuts: detect_undercuts()의 결과
        face_results: analyze_all_faces()의 결과
        distance_threshold: 같은 그룹으로 묶을 최대 거리 (mm)
        angle_threshold: 같은 그룹으로 묶을 최대 법선 각도 차이 (도)

    Returns:
        list of groups, each group is a dict with faces, direction, etc.
    """
    if not undercuts:
        return []

    # 각 언더컷의 법선/위치 정보 수집
    result_map = {r["face_id"]: r for r in face_results}
    uc_data = []
    for uc in undercuts:
        fid = uc["face_id"]
        result = result_map.get(fid, {})
        normals = result.get("normals", [])
        center = np.array(uc["center"])

        if normals:
            avg_normal = np.mean(normals, axis=0)
            # 수평 성분만 (Z 제거)
            horizontal = np.array([avg_normal[0], avg_normal[1], 0])
            h_norm = np.linalg.norm(horizontal)
            if h_norm > 1e-10:
                horizontal = horizontal / h_norm
            else:
                horizontal = np.array([0, 0, 0])
        else:
            horizontal = np.array([0, 0, 0])

        uc_data.append({
            "face_id": fid,
            "center": center,
            "horizontal_dir": horizontal,
            "normals": normals,
            "area": uc["area"],
            "surface_type": uc["surface_type"],
            "reason": uc["reason"],
        })

    # 간단한 클러스터링: 거리 + 방향 유사도 기반
    used = [False] * len(uc_data)
    groups = []

    for i, data_i in enumerate(uc_data):
        if used[i]:
            continue

        group_faces = [data_i]
        used[i] = True

        for j, data_j in enumerate(uc_data):
            if used[j]:
                continue

            # 거리 체크
            dist = np.linalg.norm(data_i["center"] - data_j["center"])
            if dist > distance_threshold:
                continue

            # 방향 유사도 체크
            if np.linalg.norm(data_i["horizontal_dir"]) > 0.1 and \
               np.linalg.norm(data_j["horizontal_dir"]) > 0.1:
                dot = abs(np.dot(data_i["horizontal_dir"], data_j["horizontal_dir"]))
                angle = math.degrees(math.acos(min(dot, 1.0)))
                if angle > angle_threshold:
                    continue

            group_faces.append(data_j)
            used[j] = True

        groups.append(group_faces)

    return groups


# ─── 슬라이드 코어 분석 ────────────────────────────

def analyze_slide_cores(groups: list, bbox: dict, parting_z: float) -> list:
    """각 그룹에 대해 슬라이드 코어 상세 분석을 수행합니다.

    Returns:
        list of slide_core dicts
    """
    slides = []

    for group_idx, group in enumerate(groups):
        # 그룹의 모든 법선 수집
        all_normals = []
        all_centers = []
        total_area = 0

        for face_data in group:
            all_normals.extend(face_data["normals"])
            all_centers.append(face_data["center"])
            total_area += face_data["area"]

        if not all_normals:
            continue

        np_normals = np.array(all_normals)
        np_centers = np.array(all_centers)

        # ── 슬라이드 방향 계산 ──
        slide_dir = _compute_slide_direction(all_normals)
        dir_name, canonical_dir = _nearest_canonical(slide_dir)

        # ── 슬라이드 영역 바운딩 박스 ──
        group_min = np_centers.min(axis=0)
        group_max = np_centers.max(axis=0)
        group_center = np_centers.mean(axis=0)

        # ── 언더컷 깊이 (슬라이드 방향 성분) ──
        projections = []
        for center in all_centers:
            proj = np.dot(center - group_center, canonical_dir)
            projections.append(abs(proj))

        undercut_depth = max(projections) if projections else 5.0
        undercut_depth = max(undercut_depth, 2.0)  # 최소 2mm

        # ── 슬라이드 이동 거리 (stroke) ──
        # 언더컷 깊이 + 안전 여유 (3mm) + 클리어런스
        stroke = undercut_depth + 3.0

        # ── 슬라이드 크기 추정 ──
        dx = group_max[0] - group_min[0] + 10  # 양쪽 5mm 여유
        dy = group_max[1] - group_min[1] + 10
        dz = group_max[2] - group_min[2] + 10

        # 슬라이드 방향에 따라 크기 조정
        if abs(canonical_dir[0]) > 0.5:  # X 방향 슬라이드
            slide_width = dy
            slide_height = dz
            slide_length = stroke + 15  # 슬라이드 본체 길이
        else:  # Y 방향 슬라이드
            slide_width = dx
            slide_height = dz
            slide_length = stroke + 15

        # ── 슬라이드 vs 경사코어 판단 ──
        # 파팅라인 근처 + 면적 작음 → 경사코어(리프터) 가능
        avg_z = group_center[2]
        near_parting = abs(avg_z - parting_z) < bbox.get("dz", 100) * 0.15
        small_area = total_area < 100  # mm²

        if near_parting and small_area:
            core_type = "lifter"
            core_type_kr = "경사 코어 (리프터)"
            core_reason = "파팅라인 근처 + 작은 면적 → 경사 코어 추천"
        elif near_parting:
            core_type = "lifter_or_slide"
            core_type_kr = "경사 코어 또는 슬라이드"
            core_reason = "파팅라인 근처, 면적에 따라 선택"
        else:
            core_type = "slide"
            core_type_kr = "슬라이드 코어"
            core_reason = "파팅라인에서 먼 언더컷 → 슬라이드 코어 필요"

        # ── 앵귤러 핀 각도 추정 ──
        # 일반적으로 15~25도. stroke에 따라 조정
        angular_pin_angle = min(25, max(15, math.degrees(math.atan2(stroke, 40))))

        slides.append({
            "id": group_idx + 1,
            "core_type": core_type,
            "core_type_kr": core_type_kr,
            "core_reason": core_reason,
            "direction_name": dir_name,
            "direction_vector": canonical_dir.tolist(),
            "slide_dir_raw": slide_dir.tolist(),
            "face_ids": [f["face_id"] for f in group],
            "face_count": len(group),
            "center": group_center.tolist(),
            "bbox_min": group_min.tolist(),
            "bbox_max": group_max.tolist(),
            "total_area": total_area,
            "undercut_depth": undercut_depth,
            "stroke": stroke,
            "slide_size": {
                "width": slide_width,
                "height": slide_height,
                "length": slide_length,
            },
            "angular_pin_angle": angular_pin_angle,
            "near_parting": near_parting,
        })

    # 면적 기준 내림차순 정렬
    slides.sort(key=lambda s: s["total_area"], reverse=True)

    return slides


# ─── 금형 레이아웃 요약 ─────────────────────────────

def generate_mold_layout(slides: list, bbox: dict, parting_z: float) -> dict:
    """전체 금형 레이아웃을 요약합니다.

    Returns:
        dict with mold layout summary
    """
    # 방향별 슬라이드 수
    direction_counts = {}
    for s in slides:
        d = s["direction_name"]
        direction_counts[d] = direction_counts.get(d, 0) + 1

    # 슬라이드 유형별 수
    type_counts = {}
    for s in slides:
        t = s["core_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # 금형 크기 추정 (부품 + 슬라이드 여유)
    max_stroke = max((s["stroke"] for s in slides), default=0)
    mold_width = bbox["dx"] + max_stroke * 2 + 60   # 양쪽 슬라이드 + 프레임
    mold_depth = bbox["dy"] + max_stroke * 2 + 60
    mold_height = bbox["dz"] + 40  # 상하 여유

    # 금형 복잡도 판정
    total_slides = len(slides)
    if total_slides == 0:
        complexity = "단순 (2판 금형)"
        complexity_detail = "슬라이드 없이 상/하 금형으로 성형 가능"
    elif total_slides <= 2:
        complexity = "보통 (슬라이드 금형)"
        complexity_detail = f"{total_slides}개 슬라이드 코어 필요"
    elif total_slides <= 4:
        complexity = "복잡 (다방향 슬라이드)"
        complexity_detail = f"{total_slides}개 슬라이드, 금형비 증가 예상"
    else:
        complexity = "매우 복잡"
        complexity_detail = f"{total_slides}개 슬라이드, 설계 변경 검토 권장"

    return {
        "total_slides": total_slides,
        "direction_counts": direction_counts,
        "type_counts": type_counts,
        "complexity": complexity,
        "complexity_detail": complexity_detail,
        "estimated_mold_size": {
            "width": mold_width,
            "depth": mold_depth,
            "height": mold_height,
        },
        "parting_z": parting_z,
        "max_stroke": max_stroke,
    }


# ─── 메인 분석 함수 ────────────────────────────────

def analyze_slides(undercuts: list, face_results: list,
                   bbox: dict, parting_z: float) -> tuple:
    """슬라이드 코어 전체 분석을 수행합니다.

    Returns:
        (slides, mold_layout)
    """
    groups = group_undercuts(undercuts, face_results)
    slides = analyze_slide_cores(groups, bbox, parting_z)
    layout = generate_mold_layout(slides, bbox, parting_z)

    return slides, layout
