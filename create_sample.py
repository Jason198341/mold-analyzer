"""테스트용 샘플 STEP 파일 생성 스크립트.

간단한 사출 부품 형상을 만들어 sample.step으로 저장합니다.
"""

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.Interface import Interface_Static


def create_sample_part():
    """간단한 사출 성형 부품: 박스 + 보스 + 구멍."""

    # 1. 기본 박스 (50 x 30 x 20 mm)
    box = BRepPrimAPI_MakeBox(gp_Pnt(-25, -15, 0), 50, 30, 20).Shape()

    # 2. 상단에 원통형 보스 추가 (지름 10mm, 높이 8mm)
    boss_ax = gp_Ax2(gp_Pnt(0, 0, 20), gp_Dir(0, 0, 1))
    boss = BRepPrimAPI_MakeCylinder(boss_ax, 5, 8).Shape()
    shape = BRepAlgoAPI_Fuse(box, boss).Shape()

    # 3. 내부 구멍 (보스 안쪽, 지름 6mm)
    hole_ax = gp_Ax2(gp_Pnt(0, 0, 15), gp_Dir(0, 0, 1))
    hole = BRepPrimAPI_MakeCylinder(hole_ax, 3, 15).Shape()
    shape = BRepAlgoAPI_Cut(shape, hole).Shape()

    # 4. 필렛 적용
    try:
        fillet = BRepFilletAPI_MakeFillet(shape)
        explorer = TopExp_Explorer(shape, TopAbs_EDGE)
        count = 0
        while explorer.More() and count < 4:
            edge = TopoDS.Edge_s(explorer.Current())
            fillet.Add(1.5, edge)
            count += 1
            explorer.Next()
        if fillet.IsDone():
            shape = fillet.Shape()
    except Exception:
        pass

    return shape


def save_step(shape, filename="sample.step"):
    """Shape을 STEP 파일로 저장합니다."""
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filename)

    if status == 1:
        print(f"  sample STEP file created: {filename}")
        print(f"  -> python analyze.py {filename}")
    else:
        print(f"  STEP save failed (status={status})")


if __name__ == "__main__":
    print("Creating sample injection molding part...")
    shape = create_sample_part()
    save_step(shape)
