from collectors.google_news_collector import collect_google_news
from collectors.github_releases_collector import collect_github_releases
from collectors.hacker_news_collector import collect_hacker_news
from collectors.manual_csv_collector import collect_manual_csv
from collectors.reddit_collector import collect_reddit
from collectors.rss_collector import collect_rss
from collectors.tiktok_public_collector import collect_tiktok_public
from collectors.x_collector import collect_x
from collectors.youtube_collector import collect_youtube


COLLECTORS = {
    "youtube": collect_youtube,
    "google_news": collect_google_news,
    "github_releases": collect_github_releases,
    "hacker_news": collect_hacker_news,
    "reddit": collect_reddit,
    "rss": collect_rss,
    "x": collect_x,
    "tiktok": collect_tiktok_public,
    "manual_csv": collect_manual_csv,
}
