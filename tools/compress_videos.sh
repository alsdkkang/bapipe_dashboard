#!/usr/bin/env bash
# Batch-compress behaviour videos for upload (CRF re-encode).
#
# Shrinks file size by lowering the video bitrate ONLY — resolution, frame count
# and fps are preserved, so DLC .h5 keypoint coordinates still line up exactly and
# every analysis result is identical. Audio is dropped (behaviour videos don't use
# it). Output goes to a sibling folder; originals are never touched.
#
# Usage:
#   tools/compress_videos.sh <input_dir> [output_dir] [crf]
#
# Examples:
#   tools/compress_videos.sh ~/data/v4/videos
#   tools/compress_videos.sh ~/data/v4/videos ~/data/v4/videos_small 26
#
# CRF guide (lower = better quality, bigger file):
#   23 = default    26 = recommended (good visuals, much smaller)    28 = smallest
#   Analysis reads the .h5 files, not the pixels, so even 28 is fine for the numbers;
#   26 keeps clips / corner-picking looking clean.

set -euo pipefail

IN="${1:?Usage: compress_videos.sh <input_dir> [output_dir] [crf]}"
OUT="${2:-${IN%/}_crf}"
CRF="${3:-26}"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found — install with: brew install ffmpeg"; exit 1; }

hsize() { awk -v b="$1" 'BEGIN{u="B KB MB GB TB";split(u,a," ");
  for(i=1;b>=1024&&i<5;i++)b/=1024; printf (b>=10||i==1)?"%.0f%s":"%.1f%s",b,a[i]}'; }

mkdir -p "$OUT"
shopt -s nullglob nocaseglob
files=("$IN"/*.mp4 "$IN"/*.avi "$IN"/*.mov "$IN"/*.mkv)
(( ${#files[@]} )) || { echo "No videos (.mp4/.avi/.mov/.mkv) in: $IN"; exit 1; }

echo "Compressing ${#files[@]} video(s)  CRF=$CRF"
echo "  from: $IN"
echo "  to:   $OUT"
echo

total_in=0; total_out=0
for f in "${files[@]}"; do
  base="$(basename "${f%.*}").mp4"          # normalise every container to .mp4
  dest="$OUT/$base"
  ffmpeg -nostdin -loglevel error -y -i "$f" \
         -c:v libx264 -crf "$CRF" -preset medium -pix_fmt yuv420p -an "$dest"
  in_b=$(stat -f%z "$f"); out_b=$(stat -f%z "$dest")
  total_in=$((total_in+in_b)); total_out=$((total_out+out_b))
  printf "  %-40s %8s → %8s\n" "$(basename "$f")" "$(hsize "$in_b")" "$(hsize "$out_b")"
done

echo
pct=$(awk -v o="$total_out" -v i="$total_in" 'BEGIN{printf "%.0f", (i? o*100/i : 0)}')
printf "Done.  Total: %s → %s  (%s%% of original)\n" \
  "$(hsize "$total_in")" "$(hsize "$total_out")" "$pct"
echo "Upload the files in: $OUT   (keep your .h5 / metadata as-is)"
