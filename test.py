import anki
import asyncio
import random
import pygame
try:
    from .UiMain import Ui
    from .Design import Design
except ImportError:
    from UiMain import Ui
    from Design import Design


async def main():
    print("Start")
    pygame.init()
    with Ui([],fakeMap(),(1,0),False) as Uiob:
        await Uiob.waitForSetupAsync()
        Uiob.addEvent("test")
        while True:
            await asyncio.sleep(10)
            #des = randDes()
            #Uiob.setDesign(des)
            #print(des)

def fakeMap():
    from anki import TrackPieceType
    t = lambda type, clockwise: anki.TrackPiece(0, type, clockwise)
    map = [
        t(TrackPieceType.START, False),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.STRAIGHT, True),
        t(TrackPieceType.CURVE, False),
        t(TrackPieceType.CURVE, False),
        t(TrackPieceType.INTERSECTION, False),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.CURVE, True),
        t(TrackPieceType.INTERSECTION, False),
        t(TrackPieceType.FINISH, False),
    ]
    return map

if __name__ == "__main__":
    asyncio.run(main())