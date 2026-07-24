from storage.config_store import ConfigStore


def notify(title: str, message: str, config: ConfigStore) -> None:
    if not config.get("notifications_enabled"):
        return
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="FaceWatch",
            timeout=5,
        )
    except Exception:
        pass
