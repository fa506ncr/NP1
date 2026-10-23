"""Rebuild the original BNE demo artwork and little synthesized soundtrack.

Only pygame-ce and Python's standard library are needed. No downloaded art or music.
Run from any directory: python tools/make_demo_assets.py
"""

import math
import random
import struct
import wave
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1] / "game"
SCALE = 2


class Art:
    def __init__(self, width=1280, height=720, transparent=False):
        self.width, self.height = width, height
        self.surface = pygame.Surface((width * SCALE, height * SCALE), pygame.SRCALPHA)
        if not transparent:
            self.surface.fill((18, 35, 50))

    def point(self, point):
        return tuple(round(value * SCALE) for value in point)

    def rect(self, color, rect, radius=0, width=0):
        pygame.draw.rect(
            self.surface,
            color,
            pygame.Rect(*(round(n * SCALE) for n in rect)),
            round(width * SCALE),
            border_radius=round(radius * SCALE),
        )

    def poly(self, color, points, width=0):
        pygame.draw.polygon(
            self.surface, color, [self.point(point) for point in points], round(width * SCALE)
        )

    def ellipse(self, color, rect, width=0):
        pygame.draw.ellipse(
            self.surface,
            color,
            pygame.Rect(*(round(n * SCALE) for n in rect)),
            round(width * SCALE),
        )

    def circle(self, color, center, radius, width=0):
        pygame.draw.circle(
            self.surface, color, self.point(center), round(radius * SCALE), round(width * SCALE)
        )

    def line(self, color, start, end, width=1):
        pygame.draw.line(
            self.surface, color, self.point(start), self.point(end), max(1, round(width * SCALE))
        )

    def curve(self, color, points, width=1):
        # Cubic Bezier, sampled in logical coordinates for reproducible smooth shapes.
        curve = []
        for i in range(61):
            t = i / 60
            weights = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t**3)
            curve.append(
                tuple(
                    sum(p[axis] * weight for p, weight in zip(points, weights, strict=True))
                    for axis in (0, 1)
                )
            )
        pygame.draw.lines(
            self.surface, color, False, [self.point(p) for p in curve], max(1, round(width * SCALE))
        )

    def glow(self, center, radius, color, opacity=80):
        size = round(radius * 2 * SCALE)
        layer = pygame.Surface((size, size), pygame.SRCALPHA)
        for r in range(round(radius * SCALE), 0, -2):
            alpha = round(opacity * (1 - r / (radius * SCALE)) ** 1.5)
            pygame.draw.circle(layer, (*color, alpha), (size // 2, size // 2), r)
        self.surface.blit(layer, self.point((center[0] - radius, center[1] - radius)))

    def gradient(self, stops):
        for y in range(self.height * SCALE):
            logical = y / SCALE
            for (y1, c1), (y2, c2) in zip(stops, stops[1:], strict=False):
                if y1 <= logical <= y2:
                    ratio = (logical - y1) / (y2 - y1)
                    color = tuple(round(a + (b - a) * ratio) for a, b in zip(c1, c2, strict=True))
                    pygame.draw.line(self.surface, color, (0, y), (self.width * SCALE, y))
                    break

    def text(self, value, x, y, size, color, spacing=0):
        font = pygame.font.Font(str(ROOT / "gui/DejaVuSans.ttf"), round(size * SCALE))
        if not spacing:
            self.surface.blit(font.render(value, True, color), self.point((x, y)))
            return
        for char in value:
            self.surface.blit(font.render(char, True, color), self.point((x, y)))
            x += font.size(char)[0] / SCALE + spacing

    def grain(self, seed):
        randomizer = random.Random(seed)
        layer = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        for _ in range(32_000):
            x = randomizer.randrange(self.width * SCALE)
            y = randomizer.randrange(self.height * SCALE)
            layer.set_at((x, y), (211, 225, 220, randomizer.randrange(3, 18)))
        self.surface.blit(layer, (0, 0))

    def save(self, relative):
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image = pygame.transform.smoothscale(self.surface, (self.width, self.height))
        pygame.image.save(image, str(path))
        print(path.relative_to(ROOT.parent))


def star(art, x, y, size=4, color=(229, 222, 183)):
    art.line(color, (x - size, y), (x + size, y))
    art.line(color, (x, y - size), (x, y + size))
    art.circle(color, (x, y), max(1, size / 4))


def windows(art, x, y, columns, rows, w=17, h=30, gapx=34, gapy=54, seed=1):
    randomizer = random.Random(seed)
    for row in range(rows):
        for col in range(columns):
            left, top = x + col * gapx, y + row * gapy
            lit = randomizer.random() > 0.22
            art.rect((24, 47, 58), (left - 3, top - 3, w + 6, h + 6), 2)
            art.rect((224, 184, 132) if lit else (69, 93, 103), (left, top, w, h), 2)
            if lit:
                art.rect((246, 216, 163), (left + 2, top + 2, w - 4, h * 0.6), 1)
            art.line((68, 74, 73), (left + w / 2, top), (left + w / 2, top + h), 1.5)


def lamp(art, x, ground, height=200):
    top = ground - height
    art.line((24, 46, 55), (x, ground), (x, top), 7)
    art.rect((33, 56, 63), (x - 13, ground - 8, 26, 8), 2)
    art.glow((x, top + 12), 72, (246, 205, 139), 110)
    art.poly(
        (27, 49, 57), [(x - 20, top - 3), (x + 20, top - 3), (x + 12, top + 32), (x - 12, top + 32)]
    )
    art.poly(
        (247, 220, 164),
        [(x - 14, top + 2), (x + 14, top + 2), (x + 9, top + 25), (x - 9, top + 25)],
    )
    art.poly((26, 45, 55), [(x - 25, top), (x, top - 18), (x + 25, top)])
    art.line((47, 63, 64), (x, top + 2), (x, top + 25), 2)


def station():
    art = Art()
    art.gradient(
        [
            (0, (32, 57, 80)),
            (260, (115, 111, 133)),
            (440, (207, 159, 143)),
            (470, (68, 86, 94)),
            (720, (20, 44, 57)),
        ]
    )
    art.glow((927, 255), 240, (241, 174, 128), 65)
    art.circle((238, 218, 173), (1044, 124), 27)
    art.circle((44, 66, 86), (1034, 115), 26)
    for x, y in [(798, 78), (1124, 206), (722, 132), (1168, 56)]:
        star(art, x, y, 2)
    art.poly(
        (91, 104, 121),
        [
            (0, 376),
            (201, 289),
            (330, 344),
            (521, 264),
            (701, 375),
            (852, 317),
            (1044, 358),
            (1150, 308),
            (1280, 358),
            (1280, 462),
            (0, 462),
        ],
    )
    for x, height, width in [
        (620, 101, 65),
        (698, 75, 83),
        (794, 133, 56),
        (864, 94, 67),
        (956, 82, 75),
        (1140, 116, 86),
    ]:
        art.rect((70, 89, 105), (x, 422 - height, width, height))
        art.poly(
            (53, 74, 91),
            [(x - 8, 422 - height), (x + width / 2, 398 - height), (x + width + 8, 422 - height)],
        )
        windows(art, x + 10, 440 - height, 2, 2, 8, 14, 22, 28, x)
    # The platform and rails meet at the end of the station.
    art.poly((58, 78, 87), [(0, 470), (944, 418), (1280, 720), (0, 720)])
    art.poly((27, 49, 63), [(945, 422), (1280, 480), (1280, 720)])
    art.poly((130, 135, 129), [(933, 425), (941, 425), (1280, 709), (1280, 720)])
    art.poly((156, 157, 145), [(989, 430), (994, 430), (1280, 569), (1280, 578)])
    for index in range(1, 14):
        t = (index / 14) ** 1.6
        art.line(
            (55, 76, 86), (944 + 350 * t, 425 + 270 * t), (972 + 350 * t, 425 + 146 * t), 6 * t + 1
        )
    for y in [510, 566, 639, 714]:
        art.line((73, 90, 96), (0, y), (940, 425), 1)
    # Main station facade.
    art.poly((95, 104, 109), [(0, 225), (548, 282), (548, 484), (0, 529)])
    art.poly((116, 120, 117), [(30, 260), (514, 305), (514, 466), (30, 500)])
    art.poly((47, 68, 80), [(0, 205), (290, 167), (585, 277), (550, 303), (0, 250)])
    art.line((149, 146, 135), (0, 249), (548, 302), 5)
    for x in (66, 196, 326):
        y = 308 + x * 0.05
        art.rect((47, 66, 74), (x, y, 75, 137), 30)
        art.rect((225, 183, 131), (x + 7, y + 7, 61, 120), 24)
        art.line((80, 88, 83), (x + 38, y + 9), (x + 38, y + 130), 4)
        art.line((80, 88, 83), (x + 5, y + 64), (x + 70, y + 64), 4)
        art.glow((x + 38, y + 70), 77, (234, 188, 132), 24)
    art.rect((29, 55, 64), (429, 354, 57, 115), 25)
    art.line((180, 170, 140), (431, 355), (431, 467), 3)
    art.rect((25, 56, 65), (221, 278, 170, 36), 3)
    art.rect((161, 166, 142), (225, 282, 162, 28), 2, 1)
    art.text("BERL", 258, 283, 20, (233, 220, 182), 7)
    # Clock and station canopy.
    art.circle((35, 58, 68), (601, 254), 39)
    art.circle((215, 208, 176), (601, 254), 32)
    art.circle((179, 179, 152), (601, 254), 28, 1)
    art.line((58, 75, 77), (601, 254), (601, 233), 3)
    art.line((58, 75, 77), (601, 254), (618, 264), 3)
    art.circle((58, 75, 77), (601, 254), 3)
    art.poly((22, 46, 61), [(0, 52), (359, 72), (725, 186), (635, 212), (0, 117)])
    art.line((82, 111, 116), (0, 119), (633, 213), 5)
    art.line((51, 79, 89), (210, 87), (615, 209), 3)
    for x, y, bottom in [(44, 125, 567), (572, 206, 487)]:
        art.rect((26, 52, 64), (x, y, 14, bottom - y))
        art.line((85, 108, 111), (x + 2, y), (x + 2, bottom), 2)
        art.line((28, 55, 65), (x + 7, y + 94), (x + 95, y + 16), 6)
    lamp(art, 888, 458, 155)
    lamp(art, 1121, 553, 222)
    # Glints on wet stone; intentional negative space in the foreground.
    randomizer = random.Random(23)
    for _ in range(120):
        x, y = randomizer.uniform(0, 1110), randomizer.uniform(487, 715)
        length = randomizer.uniform(5, 35) * (y / 720)
        color = randomizer.choice([(73, 100, 108), (106, 125, 126), (169, 146, 123)])
        art.line(color, (x, y), (x + length, y), 0.6)
    art.ellipse((64, 91, 102), (356, 576, 292, 32))
    for i in range(6):
        art.line((137, 135, 120), (416 + i * 12, 590 + i * 2), (560 + i * 8, 590 + i * 2), 1)
    art.grain(1)
    art.save("images/backgrounds/station.png")


def square():
    art = Art()
    art.gradient(
        [
            (0, (30, 53, 78)),
            (300, (117, 117, 141)),
            (480, (194, 153, 140)),
            (485, (67, 87, 98)),
            (720, (31, 53, 68)),
        ]
    )
    art.glow((759, 322), 260, (235, 183, 144), 55)
    for x, y in [(461, 70), (917, 53), (1065, 171), (674, 119)]:
        star(art, x, y, 2)
    # Far buildings.
    for x, width, height in [
        (245, 110, 130),
        (376, 107, 164),
        (490, 95, 116),
        (880, 110, 171),
        (1007, 97, 130),
    ]:
        art.rect((81, 97, 115), (x, 468 - height, width, height))
        art.poly(
            (51, 74, 96),
            [(x - 10, 468 - height), (x + width / 2, 440 - height), (x + width + 10, 468 - height)],
        )
        windows(art, x + 16, 487 - height, 3, 2, 10, 18, 28, 40, x)
    # Observatory.
    art.rect((98, 113, 122), (699, 238, 118, 233))
    art.rect((135, 137, 136), (706, 244, 25, 225))
    art.ellipse((47, 81, 96), (679, 170, 158, 146))
    art.rect((104, 124, 128), (682, 238, 151, 29))
    art.curve((147, 164, 156), [(690, 228), (697, 165), (778, 154), (818, 223)], 3)
    art.line((186, 177, 142), (758, 174), (758, 121), 3)
    star(art, 758, 120, 9, (232, 209, 154))
    windows(art, 738, 288, 1, 3, 35, 31, 0, 55, 7)
    art.poly((55, 77, 91), [(680, 465), (839, 465), (864, 485), (654, 485)])
    # Cafe to the left, tall townhouse to the right.
    art.poly((120, 124, 121), [(0, 181), (277, 259), (277, 496), (0, 556)])
    art.poly((42, 68, 84), [(0, 151), (138, 142), (306, 251), (277, 274), (0, 195)])
    windows(art, 33, 247, 3, 2, 34, 51, 73, 99, 3)
    art.poly((67, 95, 101), [(0, 431), (282, 416), (312, 456), (0, 477)])
    for i in range(7):
        art.poly(
            (154, 156, 134),
            [
                (i * 48, 431 - i * 2),
                (i * 48 + 21, 430 - i * 2),
                (i * 48 + 35, 460 - i * 2),
                (i * 48 + 5, 463 - i * 2),
            ],
        )
    art.rect((35, 62, 73), (30, 388, 150, 35), 2)
    art.text("CAFÉ LUNE", 43, 393, 18, (226, 208, 164), 1)
    art.poly((98, 115, 122), [(1006, 257), (1280, 208), (1280, 553), (1006, 493)])
    art.poly((37, 66, 84), [(987, 260), (1145, 160), (1280, 188), (1280, 230), (1006, 278)])
    windows(art, 1043, 299, 4, 2, 32, 48, 63, 88, 45)
    for y in [282, 388, 480]:
        art.line((146, 149, 139), (1006, y), (1280, y - 42), 3)
    # Cobblestones, perspective street and fountain.
    for index in range(1, 10):
        t = index / 10
        y = 486 + t * t * 234
        art.line((77, 94, 101), (0, y), (1280, y), 1)
    for x in range(-500, 1800, 160):
        art.line((60, 83, 96), (627, 477), (x, 720), 1)
    art.ellipse((40, 65, 79), (475, 496, 355, 76))
    art.ellipse((126, 142, 143), (490, 482, 323, 70))
    art.ellipse((68, 109, 123), (503, 486, 295, 48))
    art.ellipse((154, 167, 158), (625, 437, 55, 72))
    art.rect((116, 137, 140), (638, 397, 29, 78), 8)
    art.ellipse((150, 166, 158), (585, 389, 132, 33))
    art.ellipse((97, 143, 150), (593, 391, 116, 20))
    for dx in [-55, -28, 28, 55]:
        art.curve(
            (160, 199, 197),
            [(651, 375), (651 + dx * 0.5, 333), (651 + dx * 1.6, 421), (651 + dx * 1.6, 493)],
            1.3,
        )
    art.line((191, 218, 205), (651, 391), (651, 356), 2)
    # Small trees and festoon lights.
    for x, y in [(324, 449), (936, 445)]:
        art.line((46, 68, 77), (x, y + 48), (x, y - 93), 8)
        for dx, dy, r in [(-23, -93, 32), (14, -104, 40), (31, -70, 34), (-19, -55, 35)]:
            art.circle((42, 83, 87), (x + dx, y + dy), r)
        art.rect((72, 94, 100), (x - 29, y + 25, 58, 35), 5)
    art.curve((28, 56, 73), [(201, 208), (493, 329), (854, 329), (1091, 224)], 2)
    for i in range(16):
        t = i / 15
        x = 201 + t * 890
        y = 213 + math.sin(t * math.pi) * 82
        art.glow((x, y), 19, (242, 201, 138), 115)
        art.line((32, 57, 69), (x, y - 7), (x, y + 3), 1)
        art.ellipse((250, 217, 159), (x - 3, y, 6, 9))
    lamp(art, 392, 518, 192)
    lamp(art, 900, 532, 198)
    art.ellipse((87, 110, 118), (879, 608, 239, 15))
    art.grain(2)
    art.save("images/backgrounds/square.png")


def lookout():
    art = Art()
    art.gradient(
        [
            (0, (13, 31, 53)),
            (390, (67, 89, 114)),
            (535, (110, 122, 135)),
            (536, (50, 71, 88)),
            (720, (28, 48, 64)),
        ]
    )
    randomizer = random.Random(37)
    for _ in range(130):
        x, y = randomizer.randrange(80, 1280), randomizer.randrange(20, 393)
        size = randomizer.choice([0.7, 1, 1, 1.5])
        art.circle((161, 189, 196), (x, y), size)
    art.glow((1015, 138), 105, (184, 216, 204), 40)
    art.circle((223, 225, 195), (1015, 138), 33)
    art.circle((31, 52, 76), (1003, 125), 32)
    constellation = [(655, 91), (723, 135), (798, 93), (846, 167), (930, 186)]
    for a, b in zip(constellation, constellation[1:], strict=False):
        art.line((109, 149, 166), a, b, 0.7)
    for index, (x, y) in enumerate(constellation):
        star(art, x, y, 4 if index != 2 else 7)
    # A sleepy city, low on the horizon.
    for row in range(2):
        for x in range(-20, 1300, 55):
            h = randomizer.randrange(35, 117) + row * 6
            ground = 523 + row * 36
            color = (57, 82, 103) if row == 0 else (38, 64, 85)
            art.rect(color, (x, ground - h, 51, h))
            art.poly(color, [(x - 4, ground - h), (x + 25, ground - h - 20), (x + 55, ground - h)])
            windows(art, x + 9, ground - h + 12, 2, max(1, h // 33), 5, 9, 23, 27, x + row)
    # Dome edge, balcony and telescope.
    art.poly((20, 45, 64), [(0, 0), (114, 0), (204, 134), (256, 301), (252, 575), (0, 661)])
    art.curve((84, 114, 127), [(75, 0), (218, 169), (282, 324), (247, 572)], 6)
    art.curve((45, 76, 96), [(39, 0), (182, 169), (246, 324), (211, 572)], 2)
    art.poly((70, 87, 102), [(0, 619), (1280, 600), (1280, 720), (0, 720)])
    art.line((126, 137, 139), (0, 614), (1280, 595), 6)
    art.rect((23, 48, 67), (238, 526, 1042, 9), 3)
    for x in range(282, 1280, 74):
        art.line((28, 55, 73), (x, 535), (x, 603), 5)
        art.line((90, 118, 127), (x + 2, 536), (x + 2, 602), 1)
    # Instrument body rotated toward the constellation.
    art.line((34, 56, 71), (393, 457), (332, 655), 9)
    art.line((34, 56, 71), (393, 457), (470, 648), 9)
    art.line((34, 56, 71), (393, 457), (398, 641), 7)
    art.line((134, 151, 147), (394, 477), (347, 626), 2)
    art.poly((98, 141, 149), [(313, 410), (475, 314), (502, 359), (340, 452)])
    art.poly((149, 175, 169), [(314, 409), (474, 314), (480, 324), (322, 420)])
    art.poly((38, 72, 91), [(469, 310), (486, 300), (517, 353), (501, 364)])
    art.poly((190, 177, 135), [(324, 402), (338, 394), (365, 441), (351, 450)])
    art.line((33, 57, 75), (319, 434), (287, 451), 15)
    art.circle((38, 69, 86), (394, 456), 18)
    art.circle((186, 173, 133), (394, 456), 8)
    lamp(art, 1125, 609, 155)
    art.grain(3)
    art.save("images/backgrounds/lookout.png")


def mira(smile=False):
    art = Art(600, 880, transparent=True)
    outline = (28, 48, 58)
    hair = (38, 61, 70)
    skin = (232, 190, 162)
    shadow = (192, 139, 128)
    coat = (66, 121, 126)
    # Hair behind the shoulders.
    art.ellipse(outline, (166, 55, 270, 363))
    art.poly(hair, [(181, 184), (425, 178), (444, 423), (402, 499), (171, 449), (157, 347)])
    # Body, gently asymmetric to make the pose less rigid.
    art.poly(
        outline,
        [
            (220, 398),
            (371, 395),
            (457, 452),
            (488, 710),
            (454, 878),
            (123, 878),
            (105, 711),
            (130, 463),
        ],
    )
    art.poly(
        coat,
        [
            (223, 402),
            (367, 402),
            (446, 458),
            (471, 703),
            (447, 880),
            (135, 880),
            (121, 708),
            (144, 471),
        ],
    )
    art.poly((51, 99, 109), [(147, 475), (183, 512), (169, 681), (148, 831), (122, 710)])
    art.poly((91, 146, 146), [(371, 413), (435, 462), (457, 678), (419, 760), (396, 512)])
    # Neck and blouse.
    art.poly(shadow, [(261, 317), (344, 316), (352, 414), (310, 471), (250, 415)])
    art.poly(skin, [(269, 329), (337, 327), (337, 405), (305, 439), (264, 405)])
    art.poly((218, 209, 182), [(252, 409), (306, 444), (355, 409), (379, 880), (220, 880)])
    art.poly((233, 222, 195), [(264, 437), (306, 461), (340, 434), (347, 880), (251, 880)])
    for y in [550, 606, 662]:
        art.circle((161, 146, 119), (303, y), 4)
    # Lapels and a warm ochre scarf.
    art.poly((103, 153, 148), [(229, 412), (258, 426), (254, 541), (208, 490)])
    art.poly((39, 88, 101), [(366, 414), (343, 430), (350, 551), (391, 477)])
    art.poly(
        (196, 143, 91),
        [(245, 392), (281, 425), (350, 387), (365, 412), (306, 459), (255, 445), (231, 415)],
    )
    art.poly(
        (225, 177, 111), [(239, 399), (278, 424), (349, 393), (353, 410), (306, 445), (259, 433)]
    )
    art.poly((211, 159, 99), [(306, 443), (339, 425), (361, 570), (330, 550)])
    art.line((240, 198, 132), (326, 446), (347, 546), 3)
    # Ears and face.
    art.ellipse(shadow, (192, 219, 42, 69))
    art.ellipse(skin, (373, 213, 41, 69))
    art.poly(
        shadow,
        [
            (213, 157),
            (239, 113),
            (353, 111),
            (391, 168),
            (384, 276),
            (356, 328),
            (309, 361),
            (264, 339),
            (229, 299),
        ],
    )
    art.poly(
        skin,
        [
            (220, 157),
            (243, 120),
            (351, 119),
            (384, 169),
            (376, 273),
            (350, 319),
            (310, 350),
            (268, 330),
            (236, 293),
        ],
    )
    art.poly(
        (241, 203, 172),
        [
            (244, 144),
            (349, 132),
            (374, 174),
            (365, 240),
            (341, 300),
            (313, 331),
            (274, 313),
            (244, 270),
        ],
    )
    art.ellipse((228, 168, 146), (241, 267, 38, 15))
    art.ellipse((228, 168, 146), (337, 265, 35, 14))
    # Soft, unexaggerated features.
    art.curve((68, 75, 74), [(244, 218), (251, 210), (269, 210), (278, 219)], 3)
    art.curve((68, 75, 74), [(329, 217), (338, 209), (354, 209), (362, 216)], 3)
    art.ellipse((244, 231, 207), (245, 227, 33, 17))
    art.ellipse((244, 231, 207), (330, 225, 32, 17))
    art.ellipse((65, 108, 109), (258, 226, 13, 19))
    art.ellipse((65, 108, 109), (340, 224, 13, 19))
    art.ellipse((32, 62, 72), (262, 229, 6, 13))
    art.ellipse((32, 62, 72), (344, 227, 6, 13))
    art.circle((249, 239, 214), (265, 229), 2)
    art.circle((249, 239, 214), (347, 227), 2)
    art.curve((44, 62, 65), [(243, 227), (252, 222), (268, 221), (279, 228)], 2)
    art.curve((44, 62, 65), [(328, 225), (339, 220), (353, 220), (363, 225)], 2)
    art.curve((187, 133, 120), [(307, 239), (301, 258), (298, 272), (310, 274)], 1.6)
    if smile:
        art.curve((158, 98, 95), [(284, 299), (301, 314), (319, 313), (335, 296)], 2.4)
        art.curve((240, 203, 175), [(292, 307), (305, 314), (319, 309), (326, 304)], 2)
    else:
        art.curve((162, 106, 99), [(289, 301), (301, 305), (315, 306), (327, 300)], 2)
    # Side-swept fringe, a few deliberately graphic strands.
    art.poly(
        hair,
        [
            (182, 198),
            (181, 118),
            (219, 64),
            (297, 49),
            (374, 76),
            (412, 131),
            (415, 237),
            (390, 294),
            (376, 201),
            (349, 135),
            (306, 158),
            (259, 179),
            (211, 227),
        ],
    )
    art.poly((48, 75, 83), [(195, 164), (213, 98), (274, 68), (325, 72), (293, 108), (249, 139)])
    art.poly((47, 75, 82), [(362, 104), (395, 141), (397, 245), (385, 260), (376, 170)])
    art.curve((70, 98, 102), [(204, 175), (220, 122), (268, 116), (310, 87)], 2)
    art.curve((70, 98, 102), [(362, 125), (385, 177), (370, 240), (388, 306)], 2)
    art.curve((55, 85, 93), [(190, 244), (172, 308), (213, 390), (200, 436)], 3)
    art.curve((72, 100, 104), [(409, 268), (430, 329), (403, 407), (420, 442)], 2)
    # Little star earring.
    art.circle((214, 184, 124), (393, 279), 4)
    art.line((214, 184, 124), (393, 281), (393, 299), 2)
    star(art, 393, 305, 8, (233, 203, 141))
    # Notebook and hands in the foreground.
    art.poly((27, 62, 75), [(163, 604), (303, 586), (333, 789), (192, 812)])
    art.poly((61, 102, 111), [(169, 609), (294, 594), (323, 780), (198, 801)])
    art.line((192, 183, 145), (180, 612), (208, 796), 2)
    art.poly(
        (177, 168, 132),
        [
            (237, 658),
            (246, 676),
            (266, 676),
            (251, 690),
            (258, 710),
            (239, 699),
            (222, 712),
            (226, 691),
            (209, 680),
            (230, 677),
        ],
    )
    art.poly(
        shadow, [(162, 715), (191, 696), (233, 700), (251, 714), (246, 736), (203, 752), (174, 741)]
    )
    art.poly(
        skin, [(165, 711), (191, 700), (229, 705), (244, 714), (236, 730), (202, 743), (177, 733)]
    )
    for y in [713, 720, 727]:
        art.line((196, 145, 130), (200, y), (230, y - 4), 1)
    art.poly((51, 105, 116), [(124, 687), (162, 688), (182, 740), (159, 767), (126, 735)])
    art.line((119, 162, 155), (163, 698), (179, 737), 3)
    art.line((38, 87, 101), (405, 584), (408, 823), 2)
    art.rect((49, 101, 112), (360, 732, 60, 12), 2)
    art.circle((188, 177, 133), (371, 634), 5)
    art.circle((188, 177, 133), (379, 699), 5)
    art.save(f"images/characters/mira_{'smile' if smile else 'calm'}.png")


def soundtrack():
    rate, duration = 22050, 8
    chords = [
        (146.832, 174.614, 220.0),
        (116.541, 146.832, 174.614),
        (130.813, 174.614, 220.0),
        (130.813, 164.814, 195.998),
    ]
    frames = bytearray()
    for i in range(rate * duration):
        t = i / rate
        segment = min(3, int(t // 2))
        local = t % 2
        envelope = min(1, local / 0.45, (2 - local) / 0.6)
        overall = min(1, t / 0.4, (duration - t) / 0.6)
        sample = sum(
            math.sin(2 * math.pi * frequency * t) * 0.065
            + math.sin(4 * math.pi * frequency * t) * 0.012
            for frequency in chords[segment]
        )
        sample *= envelope * overall
        frames.extend(struct.pack("<h", round(sample * 32767)))
    path = ROOT / "audio/evening.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    frames = bytearray()
    for i in range(round(rate * 0.7)):
        t = i / rate
        sample = math.sin(2 * math.pi * 880 * t) + 0.35 * math.sin(2 * math.pi * 1320 * t)
        sample *= 0.22 * math.exp(-7 * t) * min(1, t / 0.01)
        frames.extend(struct.pack("<h", round(sample * 32767)))
    with wave.open(str(ROOT / "audio/chime.wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    print("game/audio/evening.wav\ngame/audio/chime.wav")


def main():
    pygame.font.init()
    station()
    square()
    lookout()
    mira()
    mira(smile=True)
    soundtrack()
    pygame.quit()


if __name__ == "__main__":
    main()
