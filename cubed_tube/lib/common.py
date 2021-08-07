
from cubed_tube.lib import schema, models


def filter_video(series: schema.ConfigSeries, video: models.Video):
    """Returns true if a video should not be saved to the database."""
    if not video.published_at:
        return True
    if video.published_at <= (series.start or 0):
        return True
    if video.video_id in (series.ignore_video_ids or []):
        return True
    if video.tombstone is not None:
        return True
    return False
