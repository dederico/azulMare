def get_video_from_payload(payload: dict) -> str | None:
    """Return a valid video URL from either Chat2Desk payload representation."""
    video_url = payload.get("video")
    if isinstance(video_url, str) and video_url.startswith(("http://", "https://")):
        return video_url

    for attachment in payload.get("attachments") or []:
        content_type = str(attachment.get("content_type") or "").lower()
        file_url = (attachment.get("file") or {}).get("url")
        if (
            content_type.startswith("video/")
            and isinstance(file_url, str)
            and file_url.startswith(("http://", "https://"))
        ):
            return file_url
    return None
