from collectors.google_news_collector import collect_google_news
from collectors.manual_csv_collector import collect_manual_csv
from collectors.reddit_collector import collect_reddit
from collectors.tiktok_public_collector import collect_tiktok_public
from collectors.web_search_collector import collect_web
from collectors.x_collector import collect_x
from collectors.youtube_collector import collect_youtube


COLLECTORS = {
    "youtube": collect_youtube,
    "google_news": collect_google_news,
    "reddit": collect_reddit,
    "web": collect_web,
    "x": collect_x,
    "tiktok": collect_tiktok_public,
    "manual_csv": collect_manual_csv,
}
