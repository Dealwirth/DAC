"""One-off generator for the DAC brand assets (icon/logo PNGs)."""
from PIL import Image, ImageDraw


def make(size: int, path: str, radius_ratio: float = 0.22) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=int(size * radius_ratio),
        fill=(35, 47, 62, 255),
    )
    cx = cy = size / 2
    ring = size * 0.34
    width = max(2, int(size * 0.075))
    d.ellipse(
        [cx - ring, cy - ring, cx + ring, cy + ring],
        outline=(255, 153, 0, 255),
        width=width,
    )
    hand = max(2, int(size * 0.05))
    d.line([cx, cy, cx, cy - ring * 0.62], fill=(255, 255, 255, 255), width=hand)
    d.line([cx, cy, cx + ring * 0.45, cy], fill=(255, 255, 255, 255), width=hand)
    img.save(path)


if __name__ == "__main__":
    make(256, "custom_components/dac/brand/icon.png")
    make(512, "custom_components/dac/brand/icon@2x.png")
    make(1280, "custom_components/dac/brand/logo.png")
    make(2560, "custom_components/dac/brand/logo@2x.png")
    print("brand assets written")
