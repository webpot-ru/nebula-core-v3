import argparse
import json
import sys
from pathlib import Path

from vectorengine_client import (
    DEFAULT_IMAGE_MODEL,
    VectorEngineError,
    call_image_generation,
    get_api_key,
    load_dotenv_file,
)


def load_prompt(metadata_path: Path) -> str:
    with metadata_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    prompt = str(metadata.get("thumbnail_prompt") or "").strip()
    text = str(metadata.get("thumbnail_text") or "").strip()
    if not prompt:
        raise VectorEngineError(f"{metadata_path} has no thumbnail_prompt.")
    if text:
        prompt = (
            f"{prompt}\n\nOverlay text to reserve clear space for: {text}. "
            "Do not render misspelled text; composition must leave room for clean text overlay."
        )
    return prompt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a thumbnail image through VectorEngine.")
    parser.add_argument("--metadata", default="youtube_metadata.json", help="Metadata JSON path.")
    parser.add_argument("--prompt", help="Direct prompt override.")
    parser.add_argument("--output", "-o", default="youtube_thumbnail.png", help="Output image path.")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL, help="VectorEngine image model.")
    parser.add_argument("--size", default="1536x864", help="Image size for VectorEngine.")
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required for live image generation.")
    parser.add_argument("--dry-run", action="store_true", help="Validate prompt without API spend.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    loaded_env_files = [path for path in args.env_file if load_dotenv_file(path)]
    prompt = args.prompt or load_prompt(Path(args.metadata))

    if args.dry_run:
        print(json.dumps({
            "status": "dry-run",
            "model": args.model,
            "size": args.size,
            "output": args.output,
            "promptCharacters": len(prompt),
            "loadedEnvFileCount": len(loaded_env_files),
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.confirm_spend:
        raise VectorEngineError(
            "Refusing to call VectorEngine image generation because this spends API credits. "
            "Re-run with --confirm-spend or use --dry-run."
        )

    key_name, _ = get_api_key()
    output = call_image_generation(
        prompt=prompt,
        output_path=args.output,
        model=args.model,
        size=args.size,
    )
    print(json.dumps({
        "status": "ok",
        "provider": "vectorengine",
        "model": args.model,
        "size": args.size,
        "output": str(output),
        "keyName": key_name,
        "loadedEnvFileCount": len(loaded_env_files),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, VectorEngineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
