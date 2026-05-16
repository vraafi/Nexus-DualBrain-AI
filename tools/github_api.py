"""
tools/github_api.py — GitHub REST API client untuk Nexus DualBrain AI

Menggantikan pemanggilan `gh` CLI dengan GitHub REST API v3 langsung.
Menggunakan GITHUB_PERSONAL_ACCESS_TOKEN dari environment.

Dokumentasi resmi: https://docs.github.com/en/rest
Rate limit: 5000 req/jam untuk authenticated request.
"""

import base64
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _get_token() -> str:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN tidak di-set di environment. "
            "Tambahkan token di secrets."
        )
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_authenticated_user() -> dict:
    """Ambil info user yang sedang login (untuk mendapat username owner)."""
    r = requests.get(f"{GITHUB_API}/user", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def create_repo(name: str, private: bool = True, auto_init: bool = True,
                description: str = "") -> dict:
    """
    Buat repository baru di akun yang sedang login.
    Return: dict respons GitHub API (berisi 'full_name', 'clone_url', dll).
    Referensi: https://docs.github.com/en/rest/repos/repos#create-a-repository-for-the-authenticated-user
    """
    payload = {
        "name": name,
        "private": private,
        "auto_init": auto_init,
        "description": description or f"Created by Nexus DualBrain AI — {name}",
    }
    r = requests.post(f"{GITHUB_API}/user/repos", json=payload,
                      headers=_headers(), timeout=30)
    if r.status_code == 422:
        data = r.json()
        errors = data.get("errors", [])
        if any(e.get("message", "").startswith("name already exists") for e in errors):
            logger.warning("[GitHub API] Repo '%s' sudah ada, digunakan kembali.", name)
            user = get_authenticated_user()
            return {"full_name": f"{user['login']}/{name}",
                    "clone_url": f"https://github.com/{user['login']}/{name}.git",
                    "already_exists": True}
    r.raise_for_status()
    data = r.json()
    logger.info("[GitHub API] Repo dibuat: %s", data.get("full_name"))
    return data


def create_issue(owner: str, repo: str, title: str, body: str,
                 labels: Optional[list] = None) -> dict:
    """
    Buat GitHub Issue baru.
    Return: dict respons (berisi 'number', 'html_url', dll).
    Referensi: https://docs.github.com/en/rest/issues/issues#create-an-issue
    """
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        json=payload, headers=_headers(), timeout=30
    )
    r.raise_for_status()
    data = r.json()
    logger.info("[GitHub API] Issue #%s dibuat: %s", data.get("number"), title)
    return data


def list_pull_requests(owner: str, repo: str, state: str = "open",
                       label: Optional[str] = None) -> list:
    """
    List pull request pada repo.
    Referensi: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests
    """
    params = {"state": state, "per_page": 10}
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        params=params, headers=_headers(), timeout=30
    )
    r.raise_for_status()
    prs = r.json()
    if label:
        prs = [pr for pr in prs
               if any(l["name"] == label for l in pr.get("labels", []))]
    return prs


def push_file(owner: str, repo: str, path: str, content: str,
              message: str = "feat: add file via Nexus DualBrain AI",
              branch: str = "main") -> dict:
    """
    Buat atau update satu file di repository via Contents API.
    Tidak memerlukan `git` di lokal — file langsung di-push via API.

    content: string teks biasa (akan di-encode base64 otomatis).
    Referensi: https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # Cek apakah file sudah ada (butuh SHA untuk update)
    sha = None
    check_r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(), timeout=15
    )
    if check_r.status_code == 200:
        sha = check_r.json().get("sha")

    payload = {
        "message": message,
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json=payload, headers=_headers(), timeout=30
    )
    r.raise_for_status()
    logger.info("[GitHub API] File '%s' berhasil di-push ke %s/%s", path, owner, repo)
    return r.json()


def push_multiple_files(owner: str, repo: str, files: dict,
                        commit_message: str = "feat: initial commit via Nexus DualBrain AI",
                        branch: str = "main") -> bool:
    """
    Push beberapa file sekaligus ke repo (satu per satu via Contents API).
    files: dict {path_di_repo: konten_string}
    Return True jika semua berhasil.
    """
    success = True
    for file_path, content in files.items():
        try:
            push_file(owner, repo, file_path, content,
                      message=commit_message, branch=branch)
            time.sleep(0.5)
        except Exception as e:
            logger.error("[GitHub API] Gagal push '%s': %s", file_path, e)
            success = False
    return success


def get_repo_info(owner: str, repo: str) -> dict:
    """Ambil informasi repository."""
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}",
                     headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def repo_exists(owner: str, repo: str) -> bool:
    """Cek apakah repo sudah ada."""
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}",
                     headers=_headers(), timeout=15)
    return r.status_code == 200
