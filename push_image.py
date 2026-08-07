#!/usr/bin/env python3
"""
push_image.py — upload a local image to GitHub and return its public raw URL.

Instagram's publishing API fetches the image from a public URL, so each generated
card must live somewhere public. This pushes it to the Hermes-agent-groups repo via
the GitHub Contents API (pure HTTPS, works on the locked VPS — no git binary needed)
and prints the raw.githubusercontent.com URL Instagram can fetch.

Reads the GitHub token from GITHUB_PAT in the environment (Nova's .env), or --pat.

Usage:
  python3 push_image.py /data/profiles/creator/posts/post.jpg
  # optional custom repo path:
  python3 push_image.py post.jpg --repo-path posts/today.jpg

Prints JSON: {"raw_url": "https://raw.githubusercontent.com/.../posts/....jpg"}
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

OWNER = "akshattandon007"
REPO = "Hermes-agent-groups"
BRANCH = "main"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="local path to the image to upload")
    ap.add_argument("--repo-path", default="", help="path within the repo (default posts/post_<ts>.jpg)")
    ap.add_argument("--pat", default=os.environ.get("GITHUB_PAT", ""))
    ap.add_argument("--message", default="add instagram post image")
    a = ap.parse_args()

    if not a.pat:
        sys.exit("No GitHub token. Set GITHUB_PAT in the environment or pass --pat.")
    if not os.path.exists(a.image):
        sys.exit(f"Image not found: {a.image}")

    repo_path = a.repo_path or f"posts/post_{int(time.time())}.jpg"

    with open(a.image, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    api = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{repo_path}"

    # If the file already exists we must pass its sha to update it.
    sha = None
    try:
        getreq = urllib.request.Request(
            api + f"?ref={BRANCH}",
            headers={"Authorization": f"Bearer {a.pat}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "nova-pusher"},
        )
        with urllib.request.urlopen(getreq, timeout=30) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        sha = None  # doesn't exist yet — that's fine

    payload = {"message": a.message, "content": content_b64, "branch": BRANCH}
    if sha:
        payload["sha"] = sha

    putreq = urllib.request.Request(
        api,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {a.pat}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "nova-pusher",
                 "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(putreq, timeout=60) as r:
            json.loads(r.read())  # commit response; we don't need the body
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub upload failed {e.code}: {e.read().decode()[:400]}")

    raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{repo_path}"
    print(json.dumps({"raw_url": raw}))


if __name__ == "__main__":
    main()
