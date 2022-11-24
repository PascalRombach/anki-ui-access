import os, sys
import math
sys.path.append(os.getcwd())

import anki, asyncio, pygame
from anki import TrackPieceTypes
import threading
from VisMapGenerator import generate

os.chdir(os.path.dirname(os.path.abspath(__file__))) #warum auch immer das nötig ist


class Ui:
    _fahrzeuge = []
    _run = True
    _map = []
    _visMap = None
    _visMapSurf = None
    _eventList : list[pygame.surface.Surface] = []
    _font = None
    _lookup = []
    
    def __init__(self, fahrzeuge: list[anki.Vehicle], map) -> None:
        self._fahrzeuge = fahrzeuge
        self._map = map
        self._visMap, self._lookup = generate(self._map)
        
        pygame.init()
        self._font = pygame.font.SysFont("Arial",20)
        
        self._thread =  threading.Thread(target=self._UiThread,daemon=True)
        self._thread.start()
    
    def kill(self):
        self._run = False
    
    def rotateSurf(self, surf: pygame.surface, orientation: tuple[int,int]):
        return pygame.transform.rotate(surf,math.degrees(math.atan2(orientation[1],orientation[0])))
    
    def gen_MapSurface(self, visMap):
        print(visMap)
        
        Gerade = pygame.image.load("Gerade.png")
        Kurve = pygame.image.load("Kurve.png")
        Kreuzung = pygame.image.load("Kreuzung.png")
        Start = pygame.image.load("Start.png")
        mapSurf = pygame.surface.Surface((len(visMap)*100, len(visMap[0])*100),pygame.SRCALPHA)
        for x in range(len(visMap)):
            for y in range(len(visMap[x])):
                for i in range(len(visMap[x][y])):
                    match visMap[x][y][i].piece.type: #rotating of map pieces to be implemented
                        case TrackPieceTypes.STRAIGHT:
                            mapSurf.blit(self.rotateSurf(Gerade,visMap[x][y][i].orientation),(x*100,y*100))
                        case TrackPieceTypes.CURVE:
                            mapSurf.blit(self.rotateSurf(Kurve,visMap[x][y][i].orientation),(x*100,y*100))
                        case TrackPieceTypes.INTERSECTION:
                            mapSurf.blit(Kreuzung ,(x*100,y*100))
                        case TrackPieceTypes.START:
                            mapSurf.blit(self.rotateSurf(Start,visMap[x][y][i].orientation),(x*100,y*100))
                        case TrackPieceTypes.FINISH:
                            pass
                    pass #add object to map
        self._visMapSurf = mapSurf
    
    def addEvent(self, text:str, color:tuple[int,int,int]):
        self._eventList.insert(0,self._font.render(text,True,color))
        if(len(self._eventList) > 5):
            self._eventList.pop(len(self._eventList)-1)
    
    def carInfo(self, fahrzeug: anki.Vehicle):
        surf = pygame.surface.Surface((500,100))
        surf.fill((200,100,200))
        surf.blit(self._font.render(f"Vehicle ID: {fahrzeug.id}",True,(0,0,0)),(10,10))
        surf.blit(self._font.render(f"Position: {fahrzeug.map_position}",True,(0,0,0)),(10,30))
        surf.blit(self._font.render(f"Lane: {fahrzeug.getLane(anki.Lane4)}",True,(0,0,0)),(10,50))
        surf.blit(self._font.render(f"Current Trackpiece: {fahrzeug.current_track_piece.type.name}",True,(0,0,0)),(10,70))
        
        return surf
    
    def carOnMap(self):
        surf = pygame.surface.Surface(self._visMapSurf.get_size(),pygame.SRCALPHA)
        for i in range(len(self._fahrzeuge)):
            x, y, _ = self._lookup[self._fahrzeuge[i].map_position]
            pygame.draw.rect(surf,(0,0,0),(x*100,y*100,10,10),1)
        return surf
    
    def _UiThread(self):
        self.addEvent("Started Ui",(0,0,0))
        self.gen_MapSurface(self._visMap)
        Ui = pygame.display.set_mode((1000,600),pygame.SCALED)
        Logo = pygame.image.load("Logo.png")
        pygame.display.set_icon(Logo)
        pygame.display.set_caption("Anki Ui Access")
        clock = pygame.time.Clock()
        
        
        run = True
        while(self._run):
            Ui.fill((100,150,100))
            Ui.blit(self._visMapSurf,(0,0))
            
            EventSurf = pygame.surface.Surface(
                (max(self._eventList,key= lambda val: val.get_size()[0]).get_size()[0] +20 , 
                200)
            ) 
            EventSurf.fill((100,150,150))
            for i in range(len(self._eventList)):
                EventSurf.blit(self._eventList[i],(10,i*20))
            Ui.blit(EventSurf,(0,self._visMapSurf.get_size()[1]))
            
            for i in range(len(self._fahrzeuge)):
                Ui.blit(self.carInfo(self._fahrzeuge[i]),(self._visMapSurf.get_size()[0],100*i))
            
            Ui.blit(self.carOnMap(),(0,0))
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._run = False
            pygame.display.update()
            clock.tick(60)
    
    pass


async def TestMain():
    print("Start")
    auto1 = await control.connectOne()
    #auto2 = await control.connectOne()
    await control.scan()
    Uiob = Ui([auto1],control.map)
    iteration = 0
    print("Constructor finished")
    await auto1.setSpeed(200)
    #await auto2.setSpeed(300)
    try:
        while True:
            await asyncio.sleep(10)
            Uiob.addEvent(f"{iteration}",(0,0,0))
            iteration += 1
    finally:
        await control.disconnectAll()

control = anki.Controller()
asyncio.run(TestMain())