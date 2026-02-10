"""CAD 파일 읽기 및 토폴로지 추출 모듈.

지원 형식:
- STEP (.step, .stp) - 완전 지원 (B-Rep)
- IGES (.igs, .iges) - 완전 지원 (B-Rep)
- STL (.stl) - 메시 기반 분석 (면 유형 구분 불가)
- 3DXML (.3dxml) - 메시 추출 후 분석
"""

import os
import zipfile
import struct
import tempfile
import numpy as np
from OCP.STEPControl import STEPControl_Reader
from OCP.IGESControl import IGESControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.StlAPI import StlAPI_Reader
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing


# ─── 파일 형식 감지 ────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".step": "step", ".stp": "step",
    ".igs": "iges", ".iges": "iges",
    ".stl": "stl",
    ".3dxml": "3dxml",
}


def detect_format(filepath: str) -> str:
    """파일 확장자로 형식을 감지합니다."""
    ext = os.path.splitext(filepath)[1].lower()
    fmt = SUPPORTED_EXTENSIONS.get(ext)
    if fmt is None:
        raise ValueError(
            f"지원하지 않는 형식: {ext}\n"
            f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS.keys())}"
        )
    return fmt


# ─── STEP 읽기 ─────────────────────────────────────

def read_step(filepath: str):
    """STEP 파일을 읽어 TopoDS_Shape를 반환합니다."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != IFSelect_RetDone:
        raise ValueError(f"STEP 파일 읽기 실패: {filepath}")
    reader.TransferRoots()
    return reader.OneShape()


# ─── IGES 읽기 ─────────────────────────────────────

def read_iges(filepath: str):
    """IGES 파일을 읽어 TopoDS_Shape를 반환합니다."""
    reader = IGESControl_Reader()
    status = reader.ReadFile(filepath)
    if status != IFSelect_RetDone:
        raise ValueError(f"IGES 파일 읽기 실패: {filepath}")
    reader.TransferRoots()
    return reader.OneShape()


# ─── STL 읽기 ──────────────────────────────────────

def read_stl(filepath: str):
    """STL 파일을 읽어 TopoDS_Shape를 반환합니다.

    STL은 삼각형 메시이므로 B-Rep 면 정보가 없습니다.
    OCC의 StlAPI_Reader로 읽어 Shape으로 변환합니다.
    """
    reader = StlAPI_Reader()
    from OCP.TopoDS import TopoDS_Shape
    shape = TopoDS_Shape()
    reader.Read(shape, filepath)

    if shape.IsNull():
        raise ValueError(f"STL 파일 읽기 실패: {filepath}")

    return shape


# ─── 3DXML 읽기 ────────────────────────────────────

def read_3dxml(filepath: str):
    """3DXML 파일에서 메시 데이터를 추출합니다.

    3DXML은 ZIP 파일 안에 XML + 메시 데이터가 들어 있습니다.
    삼각형 메시를 추출하여 OCC Shape으로 변환합니다.
    """
    if not zipfile.is_zipfile(filepath):
        raise ValueError(f"3DXML 파일이 아닙니다 (ZIP 형식이 아님): {filepath}")

    triangles = _extract_3dxml_triangles(filepath)

    if not triangles:
        raise ValueError(f"3DXML에서 메시 데이터를 찾을 수 없습니다: {filepath}")

    # 삼각형들을 임시 STL로 변환 후 OCC로 읽기
    return _triangles_to_shape(triangles)


def _extract_3dxml_triangles(filepath: str) -> list:
    """3DXML ZIP 내부에서 삼각형 데이터를 추출합니다."""
    import xml.etree.ElementTree as ET

    triangles = []  # [(v1, v2, v3), ...] 각 v는 (x, y, z)

    with zipfile.ZipFile(filepath, 'r') as zf:
        for name in zf.namelist():
            if not name.lower().endswith('.xml'):
                continue

            try:
                content = zf.read(name).decode('utf-8', errors='ignore')
                # 3DXML의 Rep3D/Faces 구조에서 삼각형 추출
                root = ET.fromstring(content)

                # 네임스페이스 처리
                ns = {}
                for elem in root.iter():
                    if '}' in elem.tag:
                        uri = elem.tag.split('}')[0].strip('{')
                        prefix = elem.tag.split('}')[1]
                        ns[prefix] = uri

                # Vertices와 Faces 탐색
                vertices = []
                for elem in root.iter():
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

                    if tag == 'Positions' or tag == 'Vertices':
                        text = elem.text or elem.get('data', '')
                        coords = _parse_float_list(text)
                        for k in range(0, len(coords) - 2, 3):
                            vertices.append((coords[k], coords[k+1], coords[k+2]))

                    elif tag == 'Triangles' or tag == 'Faces':
                        text = elem.text or elem.get('data', '')
                        indices = _parse_int_list(text)
                        for k in range(0, len(indices) - 2, 3):
                            i1, i2, i3 = indices[k], indices[k+1], indices[k+2]
                            if i1 < len(vertices) and i2 < len(vertices) and i3 < len(vertices):
                                triangles.append((vertices[i1], vertices[i2], vertices[i3]))

            except (ET.ParseError, UnicodeDecodeError, KeyError):
                continue

    return triangles


def _parse_float_list(text: str) -> list:
    """공백/쉼표 구분 float 리스트 파싱."""
    result = []
    for token in text.replace(',', ' ').split():
        try:
            result.append(float(token))
        except ValueError:
            continue
    return result


def _parse_int_list(text: str) -> list:
    """공백/쉼표 구분 int 리스트 파싱."""
    result = []
    for token in text.replace(',', ' ').split():
        try:
            result.append(int(token))
        except ValueError:
            continue
    return result


def _triangles_to_shape(triangles: list):
    """삼각형 리스트를 임시 STL 파일 → OCC Shape로 변환합니다."""
    # 바이너리 STL 생성
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp:
        tmp_path = tmp.name
        # STL 바이너리 헤더 (80 bytes)
        tmp.write(b'\x00' * 80)
        # 삼각형 개수
        tmp.write(struct.pack('<I', len(triangles)))

        for v1, v2, v3 in triangles:
            # 법선 계산
            e1 = np.array(v2) - np.array(v1)
            e2 = np.array(v3) - np.array(v1)
            normal = np.cross(e1, e2)
            norm = np.linalg.norm(normal)
            if norm > 1e-10:
                normal = normal / norm

            # 법선 (3 floats) + 3 vertices (9 floats) + attribute (2 bytes)
            tmp.write(struct.pack('<3f', *normal))
            tmp.write(struct.pack('<3f', *v1))
            tmp.write(struct.pack('<3f', *v2))
            tmp.write(struct.pack('<3f', *v3))
            tmp.write(struct.pack('<H', 0))

    try:
        shape = read_stl(tmp_path)
    finally:
        os.unlink(tmp_path)

    return shape


# ─── 통합 읽기 함수 ────────────────────────────────

def read_cad_file(filepath: str):
    """형식을 자동 감지하여 CAD 파일을 읽습니다.

    Returns:
        tuple: (shape, format_name, format_info)
    """
    fmt = detect_format(filepath)

    readers = {
        "step": (read_step, "STEP (B-Rep)", "면/곡면 유형 분석 가능"),
        "iges": (read_iges, "IGES (B-Rep)", "면/곡면 유형 분석 가능"),
        "stl": (read_stl, "STL (Mesh)", "삼각형 메시 기반, 면 유형 구분 불가"),
        "3dxml": (read_3dxml, "3DXML (Mesh)", "메시 추출 기반, 면 유형 구분 불가"),
    }

    reader_fn, name, info = readers[fmt]
    shape = reader_fn(filepath)

    return shape, name, info


# ─── 토폴로지 추출 ─────────────────────────────────

def extract_faces(shape) -> list:
    """Shape에서 모든 Face를 추출합니다."""
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return faces


def extract_edges(shape) -> list:
    """Shape에서 모든 Edge를 추출합니다."""
    edges = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edges.append(TopoDS.Edge_s(explorer.Current()))
        explorer.Next()
    return edges


def get_bounding_box(shape) -> dict:
    """Shape의 바운딩 박스를 구합니다."""
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    return {
        "xmin": xmin, "ymin": ymin, "zmin": zmin,
        "xmax": xmax, "ymax": ymax, "zmax": zmax,
        "dx": xmax - xmin,
        "dy": ymax - ymin,
        "dz": zmax - zmin,
    }


def get_shape_properties(shape) -> dict:
    """Shape의 물성 (체적, 표면적)을 계산합니다."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume = props.Mass()

    BRepGProp.SurfaceProperties_s(shape, props)
    surface_area = props.Mass()

    return {
        "volume_mm3": volume,
        "surface_area_mm2": surface_area,
    }
