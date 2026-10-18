"""Simple vector-style scene illustrations for the explicitly labelled 2D mode."""
import math


def person(draw, x, y, scale=1.0, armor=False, child=False, arm=0):
    def box(a, b, c, d):
        return [x + a * scale, y + b * scale, x + c * scale, y + d * scale]
    cloth = (130, 154, 169) if armor else (120, 70, 44)
    draw.ellipse(box(-29, -180, 29, -122), fill=(243, 196, 151), outline=(87, 53, 35), width=3)
    if armor:
        draw.pieslice(box(-34, -196, 34, -129), 180, 360, fill=(184, 194, 201))
    else:
        draw.pieslice(box(-30, -188, 30, -140), 180, 360, fill=(46, 35, 32))
    draw.rounded_rectangle(box(-32, -122, 32, -32), radius=max(2, int(8 * scale)), fill=cloth)
    draw.line([(x - 18 * scale, y - 32 * scale), (x - 24 * scale, y)], fill=cloth, width=max(1, int(18 * scale)))
    draw.line([(x + 18 * scale, y - 32 * scale), (x + 24 * scale, y)], fill=cloth, width=max(1, int(18 * scale)))
    draw.line([(x - 30 * scale, y - 108 * scale), (x - 65 * scale, y - 60 * scale)], fill=(243, 196, 151), width=max(1, int(13 * scale)))
    draw.line([(x + 30 * scale, y - 108 * scale), (x + 70 * scale, y - (90 + arm) * scale)], fill=(243, 196, 151), width=max(1, int(13 * scale)))
    draw.ellipse(box(-16, -158, -10, -151), fill=(35, 31, 28))
    draw.ellipse(box(10, -158, 16, -151), fill=(35, 31, 28))


def house(draw, x, y, scale=1, shrine=False):
    draw.rectangle([x - 120 * scale, y - 160 * scale, x + 120 * scale, y], fill=(191, 148, 89))
    draw.polygon([(x - 165 * scale, y - 150 * scale), (x, y - 265 * scale), (x + 165 * scale, y - 150 * scale)], fill=(143, 62, 44) if shrine else (176, 141, 62))
    draw.rectangle([x - 28 * scale, y - 100 * scale, x + 28 * scale, y], fill=(70, 49, 35))
    if shrine:
        for dx in (-90, 90):
            draw.rectangle([x + (dx - 12) * scale, y - 150 * scale, x + (dx + 12) * scale, y], fill=(174, 54, 38))


def bamboo(draw, x, y, scale=1):
    for dx, tip in [(-30, -270), (0, -330), (35, -290)]:
        draw.line([(x + dx * scale, y), (x + dx * scale, y + tip * scale)], fill=(119, 158, 54), width=max(1, int(10 * scale)))
        for n in range(4):
            by = y - (70 + n * 55) * scale
            draw.line([(x + (dx - 7) * scale, by), (x + (dx + 7) * scale, by)], fill=(212, 204, 107), width=3)
            draw.polygon([(x + dx * scale, by), (x + (dx + 65) * scale, by - 45 * scale), (x + (dx + 28) * scale, by - 10 * scale)], fill=(66, 116, 48))


def horse(draw, x, y, t, fire=False):
    metal = (156, 172, 187)
    draw.ellipse([x - 150, y - 130, x + 130, y - 10], fill=metal, outline=(66, 81, 97), width=5)
    draw.polygon([(x + 60, y - 90), (x + 130, y - 245), (x + 185, y - 235), (x + 145, y - 70)], fill=metal)
    draw.ellipse([x + 115, y - 260, x + 235, y - 195], fill=metal)
    draw.ellipse([x + 170, y - 240, x + 182, y - 228], fill=(239, 149, 47))
    for i, dx in enumerate((-110, -50, 60, 110)):
        swing = math.sin(t * 10 * math.pi + i * math.pi) * 30
        draw.line([(x + dx, y - 30), (x + dx + swing, y + 60)], fill=metal, width=18)
    draw.line([(x - 135, y - 90), (x - 215, y - 45)], fill=(70, 83, 102), width=15)
    if fire:
        draw.polygon([(x + 220, y - 240), (x + 360 + 25 * math.sin(t * 20), y - 210), (x + 280, y - 180), (x + 220, y - 200)], fill=(247, 117, 33))
        draw.polygon([(x + 225, y - 225), (x + 310, y - 207), (x + 228, y - 208)], fill=(255, 219, 87))


def draw_giong_scene(draw, theme, t, horizon):
    y = horizon + 65
    if theme in ("giong_village", "giong_envoy", "giong_growing"):
        house(draw, 470, y, 1.15)
        bamboo(draw, 210, y)
        bamboo(draw, 1620, y, 0.9)
        person(draw, 920, y, 0.7 + 0.6 * t if theme == "giong_growing" else 0.65, child=True)
        person(draw, 780, y, 1.15)
        if theme == "giong_envoy":
            x = 1340 - 170 * t
            person(draw, x, y, 1.3, armor=True, arm=20)
            draw.line([(x + 90, y), (x + 90, y - 350)], fill=(95, 66, 40), width=7)
            draw.polygon([(x + 90, y - 350), (x + 240, y - 320), (x + 90, y - 270)], fill=(176, 53, 43))
        if theme == "giong_growing":
            for x in (650, 1200, 1400):
                person(draw, x, y, 1.0)
                draw.ellipse([x - 45, y - 75, x + 45, y - 40], fill=(229, 198, 128))
                draw.ellipse([x - 35, y - 85, x + 35, y - 62], fill=(250, 241, 212))
    elif theme == "giong_forge":
        house(draw, 420, y, 1.1)
        draw.rectangle([550, y - 90, 780, y], fill=(91, 76, 65))
        draw.polygon([(580, y - 90), (620, y - 210 - 20 * math.sin(t * 20)), (660, y - 110), (720, y - 200), (750, y - 90)], fill=(255, 153, 47))
        person(draw, 850, y, 1.25, arm=45 + 20 * math.sin(t * 8 * math.pi))
        horse(draw, 1330, y - 30, 0)
        person(draw, 1650, y, 1.5, armor=True)
    elif theme in ("giong_battle", "giong_bamboo", "giong_ascension"):
        x = 820 + 160 * t
        if theme == "giong_ascension":
            x += t * 280
            y -= t * 300
        horse(draw, x, y - 40, t, fire=theme == "giong_battle")
        person(draw, x, y - 115, 1.4, armor=True, arm=70)
        if theme == "giong_bamboo":
            bamboo(draw, x + 160, y - 140, 0.9)
            bamboo(draw, 300, horizon + 50)
        elif theme == "giong_battle":
            draw.line([(x + 95, y - 360), (x + 250, y - 470)], fill=(198, 207, 215), width=12)
            for i in range(3):
                person(draw, 1400 + i * 130 + 160 * t, horizon + 65, 0.8, armor=True)
        else:
            for cx in (450, 1150, 1450):
                draw.ellipse([cx, 300 - 70 * t, cx + 300, 365 - 70 * t], fill=(215, 226, 232))
    elif theme == "giong_shrine":
        house(draw, 960, y, 1.55, shrine=True)
        bamboo(draw, 320, y, 1.2)
        bamboo(draw, 1560, y, 1.2)
        for x in (650, 1270):
            person(draw, x, y + 15, 0.8, arm=25)


def draw_studio_scene(draw, t, horizon):
    draw.rectangle([150, 250, 1770, horizon + 40], fill=(35, 53, 73))
    for x in (230, 460, 1370, 1600):
        draw.rounded_rectangle([x - 70, 300, x + 70, horizon], radius=12, fill=(18, 30, 44), outline=(82, 106, 130), width=3)
        for yy in range(330, horizon - 25, 45):
            draw.line([(x - 50, yy), (x + 50, yy)], fill=(64, 89, 110), width=6)
            draw.ellipse([x + 35, yy - 4, x + 42, yy + 3], fill=(76, 202, 161))
    person(draw, 800, horizon + 65, 1.5, arm=20 + 10 * math.sin(t * 6 * math.pi))
    person(draw, 1130, horizon + 65, 1.4, arm=15)
