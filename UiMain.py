import itertools
import math
from typing import Iterable
import warnings
import threading
import concurrent.futures
import asyncio
import pygame 

import anki
from anki import TrackPieceType
from anki.misc.lanes import BaseLane

from Design import Design
from VehicleControlWindow import vehicleControler
from helpers import *

try:
    from .VisMapGenerator import generate, flip_h, Vismap, Element
except ImportError:
    from VisMapGenerator import generate, flip_h, Vismap

CAR_INFO_WIDTH = 500

class Ui:    
    def __init__(self,
            vehicles: list[anki.Vehicle], 
            map,
            orientation: tuple[int, int] = (1,0),
            flip: tuple[bool, bool] = (False, False),
            showUi: bool = True,
            showController: bool = False,
            fps: int = 10,
            customLanes: list[BaseLane] = [], 
            design: Design = Design(),
            vehicleColors: Iterable[tuple[int, int, int]] = []
        ) -> None:
        self._vehicleColorIterator = itertools.chain(
            iter(vehicleColors), 
            itertools.repeat((255, 255, 255))
        )
        #Loading vehicles and Lanes
        self._vehicles = vehicles
        self._accumulatedVehicleColors = [
            next(self._vehicleColorIterator)
            for _ in range(len(vehicles))
        ]
        self._customLanes = customLanes + anki.Lane3.getAll() + anki.Lane4.getAll()
        self._laneSystem: type[BaseLane] = BaseLane( # type: ignore
            "CustomLanes",
            {
                lane.name : lane.value 
                for lane in self._customLanes
            }
        )
        #setting up map
        flip_horizontal = flip[0]
        if flip[1]:
            # Vertical flipping is 180° rotation with horizontal flipping
            flip_horizontal = not flip_horizontal
            orientation = (-orientation[0], -orientation[1])

        self._map = map
        self._visMap, self._lookup = generate(self._map, orientation)
        
        if flip_horizontal:
            self._visMap, self._lookup = flip_h(self._visMap, self._lookup)

        
        #loading aditional information
        self.showUi = showUi
        self.fps = fps
        self._design = design
        
        #starting pygame
        pygame.init()
        self._font = pygame.font.SysFont(design.Font, design.FontSize)
        # integrated event logging
        self._eventSurf: pygame.Surface
        #Ui surfaces
        self.UiSurf: pygame.Surface
        self._visMapSurf: pygame.Surface
        self._ControlButtonSurf: pygame.Surface
        self._ScrollSurf: pygame.Surface
        self._rects: tuple[pygame.Rect, pygame.Rect, pygame.Rect]
        #starting ui
        self._thread = threading.Thread(target=self.__eventWrapper,daemon=True)
        self._run = True
        self._thread.start()
        # concurrent.futures doesn not see the potential of manually created futures
        # too bad!
        self._uiSetupComplete = concurrent.futures.Future()
        self._endFuture = concurrent.futures.Future()
        #getting eventloop and starting ControlWindow
        self._eventLoop = asyncio.get_running_loop()
        self._controlThread = None
        if showController:
            self.startVehicleControlUI()
        
        self._carIMG = load_image("vehicle.png")
    
    @classmethod
    def fromController(cls,
        controller: anki.Controller,
        **kwargs
    ):
        return cls(list(controller.vehicles), controller.map, **kwargs)
    
    #generating vismap
    def genGrid(self, visMap, mapsurf) -> pygame.Surface:
        drawGridLine = lambda start, end: pygame.draw.line(
            mapsurf,
            self._design.Line,
            start,
            end,
            self._design.LineWidth
        )
        for x in range(1,len(visMap)):
            drawGridLine((x*100, 0), (x*100, len(visMap[x])*100))
        for y in range(1,len(visMap[0])):
            drawGridLine((0, y*100), (len(visMap)*100, y*100))
        return mapsurf
    def genMapSurface(self, visMap: Vismap):
        imStraight = load_image("straight.png")
        imCurve = load_image("curve.png")
        imIntersection = load_image("intersection.png")
        imStart = load_image("start.png")
        mapSurf = pygame.surface.Surface((len(visMap)*100, len(visMap[0])*100),pygame.SRCALPHA)
        for (i, y, x), current in enumerated_flatten(visMap):
            current: Element
            match current.piece.type:
                case TrackPieceType.STRAIGHT:
                    imStraight.set_alpha(int((1.5**-i)*255))
                    mapSurf.blit(
                        rotateSurf(imStraight,current.orientation,90),
                        (x*100,y*100)
                    )
                    # mapSurf.blit(self._font.render(f"{current.orientation}",True,(100,100,100)),(x*100,y*100))
                case TrackPieceType.CURVE:
                    imCurve.set_alpha(int((1.5**-i)*255))
                    mapSurf.blit(pygame.transform.rotate(imCurve, float(current.rotation)), (x*100, y*100)) 
                    #mapSurf.blit(self._font.render(
                    #    f"{current.rotation} {current.orientation} {int(current.flipped) if current.flipped is not None else '/'}",
                    #    True,
                    #    (100,100,100)
                    #),(x*100,y*100))
                case TrackPieceType.INTERSECTION:
                    if current.orientation[0] != 0:
                        imIntersection.set_alpha(int((1.5**-i)*255))
                        mapSurf.blit(imIntersection, (x*100,y*100))
                case TrackPieceType.START:
                    imStart.set_alpha(int((1.5**-i)*255))
                    mapSurf.blit(rotateSurf(imStart,current.orientation,90),(x*100,y*100))
                    # mapSurf.blit(self._font.render(f"{current.orientation}",True,(100,100,100)),(x*100,y*100))
                case TrackPieceType.FINISH:
                    pass
        self._visMapSurf = mapSurf
        if self._design.ShowGrid:
            self._visMapSurf = self.genGrid(visMap,mapSurf)
        if self._design.ShowOutlines:
            pygame.draw.rect(
                self._visMapSurf,
                self._design.Line,
                (0, 0, len(visMap)*100, len(visMap[0])*100),
                self._design.LineWidth
            )
    
    #infos for cars
    def _blitCarInfoOnSurface(self, surf: pygame.Surface, text: str, dest: tuple[int, int]):
        surf.blit(
            self._font.render(text, True, self._design.Text),
            (
                10+dest[0]*300,
                10+dest[1]*self._design.FontSize
            )
        )
    def carInfo(self, vehicle: anki.Vehicle, number: int) -> pygame.Surface:
        surf = pygame.surface.Surface((CAR_INFO_WIDTH,20+self._design.FontSize*4))
        surf.fill(self._design.CarInfoFill)
        try:
            self._blitCarInfoOnSurface(surf, f"Vehicle ID: {vehicle.id}",(0,0))
            self._blitCarInfoOnSurface(surf, f"Number: {number}",(1,0))
            self._blitCarInfoOnSurface(surf, f"Position: {vehicle.map_position}",(0,1))
            self._blitCarInfoOnSurface(surf, f"Offset: {round(vehicle.road_offset,2)}",(1,1))
            self._blitCarInfoOnSurface(surf, f"Lane: {vehicle.get_lane(self._laneSystem)}",(0,2))
            self._blitCarInfoOnSurface(surf, f"Speed: {round(vehicle.speed,2)}", (1,2))
            self._blitCarInfoOnSurface(surf, f"Trackpiece: {vehicle.current_track_piece.type.name}",(0,3))
            pygame.draw.circle(surf,self._accumulatedVehicleColors[number],
                               (CAR_INFO_WIDTH-10-self._design.FontSize/2,10+self._design.FontSize*3.5),
                               self._design.FontSize/2)
        except (AttributeError, TypeError) as e:
            surf.fill(self._design.CarInfoFill)
            self._blitCarInfoOnSurface(surf, f"Invalid information:", (0,0))
            self._blitCarInfoOnSurface(surf, f"{e}", (0,1))
            warnings.warn(str(e))
        if self._design.ShowOutlines:
            pygame.draw.rect(surf,self._design.Line,surf.get_rect(),self._design.LineWidth)
        return surf
    def carOnMap(self) ->pygame.Surface:
        mapping = [
            [
                []
                for _ in range(len(column))
            ]
            for column in self._visMap
        ]
        
        surf = pygame.surface.Surface(self._visMapSurf.get_size(),pygame.SRCALPHA)
        for i, vehicle in enumerate(self._vehicles):
            if vehicle.map_position is None:
                # Disregard unaligned vehicles
                continue
            x, y, _ = self._lookup[vehicle.map_position]
            mapping[x][y].append(i)
        
        for x, column in enumerate(mapping):
            for y, layers in enumerate(column):
                width = 0
                for i, current in enumerate(layers):
                    text = self._font.render(
                        f"{current}",
                        True,
                        self._design.CarPosText
                    )
                    width += text.get_width()
                    surf.blit(
                        text,
                        (x*100+100-width,y*100+100-text.get_height())
                    )
                    #pygame.draw.rect(surf,(0,0,0),(x*100+100-10*(i+1),y*100+90,10,10),1)
        return surf
    def carOnStreet(self) -> pygame.Surface:
        rotationToDirection: dict[int,tuple[int,int]] = {
            0: (1,0),
            90: (0,0),
            180: (0,1),
            270: (1,1)
        }
        
        surf = pygame.surface.Surface(self._visMapSurf.get_size(),pygame.SRCALPHA)
        for carNum, car in enumerate(self._vehicles):
            if car.map_position is None or car.road_offset is None or car.current_track_piece is None:
                # Don't show misaligned or pre-empted vehicles.
                continue
            x, y, i = self._lookup[car.map_position]
            laneOffset = (car.road_offset / 60)*(20 - 5)
            piece: Element = self._visMap[x][y][i]
            orientation = piece.orientation

            carImage = self._carIMG.copy()
            carImage.fill(self._accumulatedVehicleColors[carNum], None, pygame.BLEND_RGB_MULT)
            if car.current_track_piece.type is not TrackPieceType.CURVE:
                surf.blit(
                    rotateSurf(carImage, orientation, -90),
                    (
                        x*100+40-laneOffset*orientation[1],
                        y*100+40+laneOffset*orientation[0]
                    )
                )
            else:
                laneOffset *= -1 if piece.piece.clockwise else 1
                laneOffset += 50
                direction = rotationToDirection[piece.rotation]
                rotation = math.radians(piece.rotation)
                curveOffset = (-math.cos(math.pi/4+rotation), math.sin(math.pi/4+rotation))
                carImage = pygame.transform.rotate(
                    carImage,
                    piece.rotation - 135 + (180 if piece.piece.clockwise else 0)
                )
                surf.blit(
                    carImage,
                    (
                        x*100 - carImage.get_width()/2  + 100*direction[0] + curveOffset[0]*laneOffset,
                        y*100 - carImage.get_height()/2 + 100*direction[1] + curveOffset[1]*laneOffset
                    )
                )
                # TODO: Remove this when no longer required (added for testing purposes)
                # pygame.draw.circle(surf,(255,255,255),
                #                 (x*100+50,
                #                  y*100+50),1)
                # pygame.draw.circle(surf,(0,255,255),
                #                 (x*100 + 100* direction[0],
                #                  y*100 + 100* direction[1]),50,1)
                # pygame.draw.circle(surf,(255,0,0),
                #                 (x*100 + 100* direction[0] + curveOffset[0]*50,
                #                  y*100 + 100* direction[1] + curveOffset[1]*50),1)
                # pygame.draw.circle(surf,(255,0,255),
                #                 (x*100 + 100* direction[0] + curveOffset[0]*laneOffset,
                #                  y*100 + 100* direction[1] + curveOffset[1]*laneOffset),2)
        return surf

    def genButtons(self):
        # NOTE: Pygame sucks. You can't render fonts with translucent background.
        # You _can_ render fonts with transparent background though, 
        # so this blitting nonsense works while a background colour doesn't.
        BtnText = self._font.render("Controller", True, self._design.Text)
        Button = pygame.surface.Surface(BtnText.get_size(), pygame.SRCALPHA)
        Button.fill(self._design.ButtonFill)
        BtnRect = BtnText.get_rect()
        if self._design.ShowOutlines:
            pygame.draw.rect(
                Button,
                self._design.Line,
                BtnRect,
                self._design.LineWidth
            )
        Button.blit(BtnText,(0,0))
        
        UpArrow = self._font.render("\u25b2",True,self._design.Text)
        DownArrow = self._font.render("\u25bc", True,self._design.Text)
        
        UpRect = UpArrow.get_rect()
        UpRect.topright = (self._visMapSurf.get_width(), 0)
        
        DownRect = DownArrow.get_rect()
        DownRect.topright = (self._visMapSurf.get_width(), UpArrow.get_height())
        
        ScrollSurf = pygame.surface.Surface(
            (UpArrow.get_width(),UpArrow.get_height()+DownArrow.get_height()),
            pygame.SRCALPHA
        )
        ScrollSurf.fill(self._design.ButtonFill)
        ScrollSurf.blit(UpArrow, (0, 0))
        ScrollSurf.blit(DownArrow, (0, UpArrow.get_height()))
        
        return (Button, ScrollSurf), (BtnRect, UpRect, DownRect)
    
    
    def updateUi(self, carInfoOffset: int, surf: pygame.Surface):
        surf.fill(self._design.Background)
        surf.blit(self._visMapSurf, (0, 0))
        
        surf.blit(self._eventSurf, (0, self._visMapSurf.get_height()))
        if self._design.ShowOutlines:
            pygame.draw.rect(
                self._eventSurf,
                self._design.Line,
                self._eventSurf.get_rect(),
                self._design.LineWidth
            )
        
        carInfoSurfs = self.getCarSurfs()
        carInfoSurfs = carInfoSurfs[carInfoOffset:]
        for i, carInfoSurf in enumerate(carInfoSurfs):
            surf.blit(carInfoSurf, (self._visMapSurf.get_width(), carInfoSurf.get_height()*i))
        
        if(self._design.ShowCarNumOnMap):
            surf.blit(self.carOnMap(), (0, 0))
        if(self._design.ShowCarOnStreet):
            surf.blit(self.carOnStreet(), (0, 0))
        return surf
    
    #The Code that showeth the Ui (:D)
    def _UiThread(self):
        self.genMapSurface(self._visMap)
        self._eventSurf = pygame.Surface((
            self._visMapSurf.get_width(),
            self._design.ConsoleHeight
        ))
        self._eventSurf.fill(self._design.EventFill)
        self.addEvent("Started Ui", self._design.Text)
        uiSize = (
            self._visMapSurf.get_width() + CAR_INFO_WIDTH,
            self._visMapSurf.get_height() + self._design.ConsoleHeight
        )
        if self.showUi:
            Logo = load_image("logo.png")
            pygame.display.set_icon(Logo)
            pygame.display.set_caption("Anki Ui Access")
            ((self._ControlButtonSurf, self._ScrollSurf), self._rects) = self.genButtons()
            Ui = pygame.display.set_mode(uiSize, pygame.SCALED)
        self.UiSurf = pygame.surface.Surface(uiSize)
        carInfoOffset = 0
        
        self._uiSetupComplete.set_result(True)
        clock = pygame.time.Clock()
        while(self._run and self.showUi):
            self.updateUi(carInfoOffset, self.UiSurf)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._run = False
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self._rects[0].collidepoint(pygame.mouse.get_pos()):
                        self.startVehicleControlUI()
                    if self._rects[1].collidepoint(pygame.mouse.get_pos()):
                        self._carInfoOffset = min(max(self._carInfoOffset+1, 0), len(self._vehicles)-1)
                    if self._rects[2].collidepoint(pygame.mouse.get_pos()):
                        self._carInfoOffset = min(max(self._carInfoOffset-1, 0), len(self._vehicles)-1)
                if event.type == pygame.MOUSEWHEEL:
                    carInfoOffset = min(
                        max(carInfoOffset + event.y, 0),
                        len(self._vehicles)-1
                    )
            
            if Ui.get_size() != self.UiSurf.get_size():
                Ui = pygame.display.set_mode(self.UiSurf.get_size(), pygame.SCALED)
            Ui.blit(self.UiSurf, (0, 0))
            Ui.blit(self._ControlButtonSurf, (0, 0))
            Ui.blit(self._ScrollSurf, (self._visMapSurf.get_width()-self._ScrollSurf.get_width(), 0))
            
            pygame.display.update()
            clock.tick(self.fps)
    
    
    def __eventWrapper(self):
        try:
            self._UiThread()
        except Exception as e:
            self._endFuture.set_exception(e)
        else:
            self._endFuture.set_result(True)
        finally:
            if not self._endFuture.done():
                self._endFuture.set_result(False)
    
    
    #methods for user interaction
    def kill(self):
        self._run = False
    def addEvent(self, text: str, color: tuple[int, int, int]|None = None):
        if self._eventSurf is None:
            warnings.warn("Ui.addEvent called before Ui was initialized", RuntimeWarning)
            return
        event = self._font.render(
            text,
            True,
            color if color != None else (0, 0, 0),
            self._design.EventFill
        )
        #The lines between messages when using outlines apear due to using scroll 
        # this is seen as a feature
        self._eventSurf.scroll(dy=event.get_height())
        pygame.draw.rect(
            self._eventSurf,
            self._design.EventFill,
            (0, 0, self._eventSurf.get_width(), event.get_height())
        )
        self._eventSurf.blit(event, (10, 0))
    def getUiSurf(self, surf: pygame.Surface|None=None) -> pygame.Surface: 
        return self.updateUi(0, surf or self.UiSurf)
    def getCarSurfs(self) -> list[pygame.Surface]:
        return [self.carInfo(self._vehicles[i], i) for i in range(len(self._vehicles)) ]
    def getMapsurf(self) -> pygame.Surface:
        return self._visMapSurf
    def getCarsOnMap(self) -> pygame.Surface:
        return self.carOnMap()
    def getEventSurf(self) -> pygame.Surface:
        return self._eventSurf
    def updateDesign(self):
        self.genMapSurface(self._visMap)
        self.UiSurf = pygame.surface.Surface(
            (self._visMapSurf.get_width() + self.getCarSurfs()[0].get_width(),
                self._visMapSurf.get_height() + self._design.ConsoleHeight))
        if(self.showUi):
            ((self._ControlButtonSurf, self._ScrollSurf), self._rects) = self.genButtons()
        
        old_eventSurf = self._eventSurf
        # TODO: Fix code duplication with _UiThread
        self._eventSurf = pygame.Surface((
            self._visMapSurf.get_width(),
            self._design.ConsoleHeight
        ))
        self._eventSurf.blit(old_eventSurf, (0, 0))
    def setDesign(self, design: Design):
        self._design = design
        self.updateDesign()
    
    def addVehicle(
            self,
            vehicle: anki.Vehicle,
            vehicleColor: tuple[int,int,int]|None = None
        ):
        self._vehicles.append(vehicle)
        if vehicleColor is None:
            self._accumulatedVehicleColors.append(next(self._vehicleColorIterator))
        else:
            self._accumulatedVehicleColors.append(vehicleColor)
    
    def removeVehicle(self,index: int):
        self._vehicles.pop(index)
        self._accumulatedVehicleColors.pop(index)
    
    def startVehicleControlUI(self): #modify starting condition
        if self._controlThread is None or not self._controlThread.is_alive():
            self._controlThread = threading.Thread(
                target=vehicleControler,
                args=(self._vehicles,self._eventLoop,self._customLanes),
                daemon=True
            )
            self._controlThread.start()
        else:
            warnings.warn("Attempted to start vehicle control window while already open", RuntimeWarning)
    
    def waitForFinish(self, timeout: float|None=None, *, ignoreExceptions: bool = False) -> bool:
        try:
            return self._endFuture.result(timeout)
        except TimeoutError:
            raise
        except Exception:
            if not ignoreExceptions:
                raise
            else:
                return False
    
    async def waitForFinishAsync(self, timeout: float|None=None, *, ignoreExceptions: bool = False) -> bool:
        try:
            return await asyncio.wait_for(asyncio.wrap_future(self._endFuture), timeout)
        except TimeoutError:
            raise
        except Exception:
            if not ignoreExceptions:
                raise
            else:
                return False
    
    def waitForSetup(self, timeout: float|None=None) -> bool:
        return self._uiSetupComplete.result(timeout)
    
    async def waitForSetupAsync(self) -> bool:
        return await asyncio.wrap_future(self._uiSetupComplete)
    
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, traceback,_) -> None:
        self.kill()
    pass