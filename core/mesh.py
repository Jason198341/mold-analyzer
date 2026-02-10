"""메시 추출 모듈 - 3D 시각화를 위한 삼각 메시 생성.

OCP의 BRepMesh로 Shape을 테셀레이션하고,
각 삼각형을 소속 Face의 구배각에 따라 색상 코딩합니다.
"""

import json
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.TopLoc import TopLoc_Location
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve


def _draft_to_color(avg_draft: float, category: str) -> tuple:
    """구배각에 따른 RGB 색상 (0~1 범위)."""
    if category == "horizontal":
        return (0.6, 0.6, 0.8)
    elif category == "good":
        return (0.2, 0.8, 0.3)
    elif category == "marginal":
        return (1.0, 0.85, 0.0)
    elif category == "insufficient":
        return (1.0, 0.4, 0.0)
    elif category == "zero":
        return (1.0, 0.1, 0.1)
    else:
        return (0.5, 0.5, 0.5)


def _thickness_to_color(avg_thickness: float) -> tuple:
    """벽 두께에 따른 RGB 색상 (0~1 범위).

    <0.8mm: 빨강(충전불량), 0.8~1.5: 주황, 1.5~3.0: 초록(양호),
    3.0~4.0: 노랑, >4.0: 빨강(싱크마크), 0: 회색(측정불가)
    """
    if avg_thickness <= 0:
        return (0.5, 0.5, 0.5)
    elif avg_thickness < 0.8:
        return (1.0, 0.1, 0.1)
    elif avg_thickness < 1.5:
        t = (avg_thickness - 0.8) / 0.7
        return (1.0, 0.4 + 0.4 * t, 0.0)
    elif avg_thickness < 3.0:
        return (0.2, 0.8, 0.3)
    elif avg_thickness < 4.0:
        t = (avg_thickness - 3.0) / 1.0
        return (0.8 + 0.2 * t, 0.8 - 0.4 * t, 0.0)
    else:
        return (1.0, 0.1, 0.1)


def extract_mesh(shape, face_results: list, deflection: float = 0.1,
                  thickness_data: dict = None) -> dict:
    """Shape을 테셀레이션하여 three.js용 메시 데이터를 추출합니다.

    thickness_data가 주어지면 두께 기반 색상 배열도 함께 생성합니다.
    """
    mesh = BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    mesh.Perform()

    positions = []
    colors = []
    thickness_colors = []
    normals_out = []

    result_map = {r["face_id"]: r for r in face_results}
    thickness_map = {}
    if thickness_data:
        for ft in thickness_data.get("face_thicknesses", []):
            thickness_map[ft["face_id"]] = ft

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)

        if triangulation is None:
            explorer.Next()
            face_idx += 1
            continue

        result = result_map.get(face_idx, {})
        category = result.get("draft_category", "unknown")
        avg_draft = result.get("avg_draft", 0)
        r, g, b = _draft_to_color(avg_draft, category)

        # 두께 색상
        t_info = thickness_map.get(face_idx, {})
        tr, tg, tb = _thickness_to_color(t_info.get("avg_thickness", 0))

        transformation = loc.Transformation()
        n_triangles = triangulation.NbTriangles()

        for i in range(1, n_triangles + 1):
            tri = triangulation.Triangle(i)
            idx1, idx2, idx3 = tri.Get()

            p1 = triangulation.Node(idx1).Transformed(transformation)
            p2 = triangulation.Node(idx2).Transformed(transformation)
            p3 = triangulation.Node(idx3).Transformed(transformation)

            # 삼각형 법선 (외적)
            v1x = p2.X() - p1.X()
            v1y = p2.Y() - p1.Y()
            v1z = p2.Z() - p1.Z()
            v2x = p3.X() - p1.X()
            v2y = p3.Y() - p1.Y()
            v2z = p3.Z() - p1.Z()
            nx = v1y * v2z - v1z * v2y
            ny = v1z * v2x - v1x * v2z
            nz = v1x * v2y - v1y * v2x
            length = (nx**2 + ny**2 + nz**2) ** 0.5
            if length > 1e-10:
                nx, ny, nz = nx / length, ny / length, nz / length
            else:
                nx, ny, nz = 0, 0, 1

            for p in [p1, p2, p3]:
                positions.extend([p.X(), p.Y(), p.Z()])
                colors.extend([r, g, b])
                thickness_colors.extend([tr, tg, tb])
                normals_out.extend([nx, ny, nz])

        explorer.Next()
        face_idx += 1

    result = {
        "positions": positions,
        "colors": colors,
        "normals": normals_out,
        "vertex_count": len(positions) // 3,
        "triangle_count": len(positions) // 9,
    }
    if thickness_data:
        result["thickness_colors"] = thickness_colors
    return result


def extract_parting_line_points(shape, parting_z: float,
                                tolerance: float = 1.0) -> list:
    """파팅라인 근처의 Edge 점들을 추출합니다."""
    points = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)

    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        u_start = curve.FirstParameter()
        u_end = curve.LastParameter()

        n_pts = 10
        edge_points = []
        edge_near_parting = False

        for k in range(n_pts + 1):
            u = u_start + (u_end - u_start) * k / n_pts
            pnt = curve.Value(u)
            if abs(pnt.Z() - parting_z) < tolerance:
                edge_near_parting = True
                edge_points.append([pnt.X(), pnt.Y(), pnt.Z()])

        if edge_near_parting and edge_points:
            points.extend(edge_points)

        explorer.Next()

    return points


def mesh_to_json(mesh_data: dict, parting_points: list = None) -> str:
    """메시 데이터를 JSON 문자열로 변환합니다."""
    export = {
        "positions": mesh_data["positions"],
        "colors": mesh_data["colors"],
        "normals": mesh_data["normals"],
        "vertex_count": mesh_data["vertex_count"],
        "triangle_count": mesh_data["triangle_count"],
    }
    if parting_points:
        export["parting_line"] = parting_points
    if "thickness_colors" in mesh_data:
        export["thickness_colors"] = mesh_data["thickness_colors"]
    return json.dumps(export)
