"""Assemble a series of PNG frames into an animated GIF.

Usage:
  python _makegif.py <glob_pattern> <out.gif> [--crop X Y W H] [--scale 0.5]
                     [--fps 3] [--maxw 900]

Example:
  python _makegif.py "img/farb_*.png" gif/farbmatrix.gif --crop 360 140 1180 760 --fps 3
"""
import sys
import glob
import argparse
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("out")
    ap.add_argument("--crop", nargs=4, type=int, default=None,
                    metavar=("X", "Y", "W", "H"))
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--maxw", type=int, default=900,
                    help="downscale so width <= maxw")
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--loop", type=int, default=0)
    args = ap.parse_args()

    files = sorted(glob.glob(args.pattern))
    if not files:
        print("NO FRAMES match", args.pattern)
        sys.exit(1)

    frames = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if args.crop:
            x, y, w, h = args.crop
            im = im.crop((x, y, x + w, y + h))
        frames.append(im)

    w0, h0 = frames[0].size
    scale = args.scale
    if scale is None and args.maxw and w0 > args.maxw:
        scale = args.maxw / w0
    if scale and scale != 1.0:
        frames = [im.resize((max(1, int(im.width * scale)),
                             max(1, int(im.height * scale))),
                            Image.LANCZOS) for im in frames]

    # Quantize for smaller GIFs
    pal = [im.convert("P", palette=Image.ADAPTIVE, colors=128) for im in frames]
    dur = int(1000 / args.fps)
    pal[0].save(args.out, save_all=True, append_images=pal[1:],
                duration=dur, loop=args.loop, optimize=True, disposal=2)
    print(f"GIF: {args.out}  {len(frames)} frames  {frames[0].size}  {args.fps}fps")


if __name__ == "__main__":
    main()
