import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import signal
import sys
import subprocess

class EbloScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive'
        })
        self.running = True

    def scrape_post(self, short_code):
        url = f"https://eblo.id/{short_code}"

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return None

            html = response.text

            short_code_val = self._extract_attr(html, 'data-short-code')
            owner_login = self._extract_attr(html, 'data-owner-login')
            twitch_id = self._extract_attr(html, 'data-owner-twitch-id')
            vote_score = self._extract_attr(html, 'data-vote-score')
            comments_count = self._extract_attr(html, 'data-comments-count')
            seven_tv = self._extract_attr(html, 'data-7tv-channel')
            media_type = self._extract_attr(html, 'data-media-type')
            blur = self._extract_attr(html, 'data-blur')
            is_private = self._extract_attr(html, 'data-private')

            if not media_type:
                media_type = 'unknown'

            nsfw = blur == '1'
            private = is_private == '1'
            twitch_url = f"https://twitch.tv/{owner_login}" if owner_login and owner_login != '?' else ''

            views_match = re.search(r'stat-value-muted["\s]*>(\d+)</span>', html)
            views = int(views_match.group(1)) if views_match else 0

            title_match = re.search(r'<title>([^<]+)</title>', html)
            post_title = title_match.group(1).replace(' - eblo.id', '') if title_match else 'Unknown'

            desc_match = re.search(r'<meta name="description" content="([^"]+)"', html)
            description = desc_match.group(1) if desc_match else ''

            post_image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            cover_image = post_image_match.group(1) if post_image_match else ''

            media_url = ''
            if media_type == 'video':
                video_match = re.search(r'<meta property="og:video" content="([^"]+)"', html)
                media_url = video_match.group(1) if video_match else ''
            else:
                media_file_match = re.search(r'<img[^>]*class="media-image"[^>]*src="([^"]+)"', html)
                if media_file_match:
                    media_url = media_file_match.group(1)
                else:
                    media_file_match2 = re.search(r'<div[^>]*id="media-container"[^>]*>.*?<img[^>]*src="([^"]+)"', html, re.DOTALL)
                    if media_file_match2:
                        media_url = media_file_match2.group(1)

            author_display_name = ''
            display_name_match = re.search(r'<a[^>]*class="author-name"[^>]*data-twitch-id="[^"]*"[^>]*>([^<]+)</a>', html)
            if display_name_match:
                author_display_name = display_name_match.group(1).strip()

            author_avatar = self._get_author_avatar(owner_login) if owner_login else ''

            date_match = re.search(r'author-date["\s]*>(\d{2}\.\d{2}\.\d{4})</span>', html)
            post_date = date_match.group(1) if date_match else ''

            if not owner_login:
                return None

            result = {
                "id": short_code_val if short_code_val else short_code,
                "owner": owner_login,
                "author_display_name": author_display_name if author_display_name else owner_login,
                "twitch-id": twitch_id if twitch_id else "?",
                "twitchUrl": twitch_url,
                "7tv-channel-id": seven_tv if seven_tv else "?",
                "media_type": media_type,
                "author_avatar": author_avatar,
                "is_nsfw": nsfw,
                "is_private": private,
                "post": {
                    "namePost": post_title,
                    "url": url,
                    "description": description,
                    "cover_image": cover_image,
                    "media_url": media_url,
                    "date": post_date,
                    "views": views,
                    "likes": int(vote_score) if vote_score and vote_score.isdigit() else 0,
                    "comments": int(comments_count) if comments_count and comments_count.isdigit() else 0
                }
            }

            if media_type == 'video' and media_url:
                result["post"]["videoFile"] = media_url

            return result

        except Exception as e:
            return None

    def download_video(self, video_url):
        if not video_url:
            print("[ERROR] No video URL")
            return False

        filename = video_url.split('/')[-1]
        if not filename:
            filename = f"video_{int(time.time())}.mp4"

        print(f"\n[DOWNLOAD] {filename}")
        print(f"[SOURCE] {video_url}")

        cmd = [
            "wget", "-c",
            "--header=Referer: https://eblo.id/",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "-O", filename,
            video_url
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                file_size = os.path.getsize(filename) / (1024 * 1024)
                print(f"[SUCCESS] File: {filename} ({file_size:.2f} MB)")
                return True
            else:
                print(f"[ERROR] Download failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"[ERROR] {e}")
            return False

    def download_from_code(self, code_or_url):
        if 'eblo.id/' in code_or_url:
            code = code_or_url.split('eblo.id/')[-1].split('?')[0]
        else:
            code = code_or_url.strip()

        print(f"[FETCH] Getting data for {code}...")
        result = self.scrape_post(code)

        if not result:
            print("[ERROR] Could not get post data")
            return False

        media_url = result['post'].get('media_url') or result['post'].get('videoFile')

        if not media_url:
            print("[ERROR] This post has no video")
            return False

        if result['media_type'] != 'video':
            print(f"[WARN] This is {result['media_type']}, not video")

        print(f"\n[VIDEO FOUND]")
        print(f"   Title: {result['post']['namePost']}")
        print(f"   Author: {result['author_display_name']}")
        print(f"   Twitch: {result['twitchUrl']}")

        return self.download_video(media_url)

    def _get_author_avatar(self, owner_login):
        if not owner_login or owner_login == '?':
            return ''

        try:
            profile_url = f"https://eblo.id/@{owner_login}"
            response = self.session.get(profile_url, timeout=10)
            if response.status_code == 200:
                avatar_match = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
                if avatar_match:
                    return avatar_match.group(1)

                avatar_match2 = re.search(r'<img[^>]*class="[^"]*avatar[^"]*"[^>]*src="([^"]+)"', response.text)
                if avatar_match2:
                    return avatar_match2.group(1)
            return ''
        except:
            return ''

    def _extract_attr(self, html, attr_name):
        match = re.search(rf'{attr_name}="([^"]+)"', html)
        return match.group(1) if match else None

    def generate_codes(self, length):
        chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        total = len(chars) ** length
        return chars, total

    def code_to_string(self, num, chars, length):
        result = []
        for _ in range(length):
            num, remainder = divmod(num, len(chars))
            result.append(chars[remainder])
        return ''.join(reversed(result))

    def signal_handler(self, sig, frame):
        print("\n\n[STOP] Stopping...")
        self.running = False

    def load_urls_from_file(self, filepath):
        urls = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        if 'eblo.id/' in line:
                            code = line.split('eblo.id/')[-1].split('?')[0]
                            urls.append(code)
                        else:
                            urls.append(line)
            print(f"[LOADED] {len(urls)} URLs from {filepath}")
            return urls
        except Exception as e:
            print(f"[ERROR] {e}")
            return []

    def scrape_from_file(self, filepath, max_threads=20):
        codes = self.load_urls_from_file(filepath)
        if not codes:
            return

        print(f"\n[START] Scraping {len(codes)} URLs...")
        print(f"[THREADS] {max_threads}")

        results = []
        found_count = 0
        failed_count = 0

        output_file = "allScrapedBytheshadowstrangers.json"
        existing_ids = set()
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    for item in existing:
                        existing_ids.add(item.get('id'))
                    results = existing
                    found_count = len(results)
                print(f"[LOADED] {found_count} existing entries")
            except:
                pass

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {}
            for code in codes:
                if code in existing_ids:
                    print(f"[SKIP] {code} already exists")
                    continue
                future = executor.submit(self.scrape_post, code)
                futures[future] = code

            for future in as_completed(futures):
                code = futures[future]
                result = future.result()
                if result:
                    results.append(result)
                    found_count += 1
                    nsfw_mark = "[NSFW]" if result['is_nsfw'] else ""
                    print(f"[OK] [{found_count}] {nsfw_mark} {code} | {result['owner']} | LIKES:{result['post']['likes']} | VIEWS:{result['post']['views']} | {result['twitchUrl']}")
                else:
                    failed_count += 1
                    print(f"[FAIL] {code}")
                self._save_results(results, output_file)

        print(f"\n[DONE] Found: {found_count}, Failed: {failed_count}")
        return results

    def bruteforce_scrape(self, min_length=6, max_length=7, max_threads=20, save_interval=100):
        signal.signal(signal.SIGINT, self.signal_handler)

        results = []
        found_count = 0

        output_file = "allScrapedBytheshadowstrangers.json"
        existing_ids = set()
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    for item in existing:
                        existing_ids.add(item.get('id'))
                    results = existing
                    found_count = len(results)
                print(f"[LOADED] {found_count} existing entries")
            except:
                pass

        print(f"\n[START] Bruteforce scraping...")
        print(f"[LENGTH] {min_length}-{max_length}")
        print(f"[CTRL+C] to stop")

        length = min_length
        while self.running and length <= max_length:
            chars, total = self.generate_codes(length)
            print(f"\n[PROCESSING] Length {length} (total {total:,} combinations)")

            processed_count = 0
            last_save = 0

            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = {}
                for i in range(total):
                    if not self.running:
                        break
                    code = self.code_to_string(i, chars, length)
                    if code in existing_ids:
                        processed_count += 1
                        continue
                    future = executor.submit(self.scrape_post, code)
                    futures[future] = code

                    if len(futures) >= max_threads * 2:
                        for f in as_completed(list(futures.keys())[:max_threads]):
                            if not self.running:
                                break
                            code_done = futures.pop(f)
                            processed_count += 1
                            result = f.result()
                            if result:
                                results.append(result)
                                found_count += 1
                                existing_ids.add(code_done)
                                nsfw_mark = "[NSFW]" if result['is_nsfw'] else ""
                                print(f"[OK] [{found_count}] {nsfw_mark} {code_done} | {result['owner']} | LIKES:{result['post']['likes']} | VIEWS:{result['post']['views']} | {result['twitchUrl']}")
                            if found_count - last_save >= save_interval:
                                self._save_results(results, output_file)
                                last_save = found_count
                    if not self.running:
                        break

                for f in as_completed(futures):
                    if not self.running:
                        break
                    result = f.result()
                    if result:
                        results.append(result)
                        found_count += 1
                        print(f"[OK] [{found_count}] {futures[f]} | {result['owner']} | {result['twitchUrl']}")
                    if found_count - last_save >= save_interval:
                        self._save_results(results, output_file)
                        last_save = found_count

            self._save_results(results, output_file)
            if self.running:
                length += 1

        print(f"\n[DONE] Found: {found_count}")
        return results

    def _save_results(self, results, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    def custom_scrape(self, url_or_code):
        if 'eblo.id/' in url_or_code:
            code = url_or_code.split('eblo.id/')[-1].split('?')[0]
        else:
            code = url_or_code.strip()

        print(f"[SCRAPE] {code}")
        result = self.scrape_post(code)

        if result:
            print("\n" + "=" * 55)
            print("RESULT:")
            print(f"   ID:              {result['id']}")
            print(f"   Owner:           {result['owner']}")
            print(f"   Display name:    {result['author_display_name']}")
            print(f"   Twitch ID:       {result['twitch-id']}")
            print(f"   Twitch URL:      {result['twitchUrl']}")
            print(f"   7TV ID:          {result['7tv-channel-id']}")
            print(f"   Type:            {result['media_type']}")
            print(f"   NSFW:            {result['is_nsfw']}")
            print(f"   Private:         {result['is_private']}")
            print(f"   Title:           {result['post']['namePost']}")
            print(f"   Date:            {result['post']['date']}")
            print(f"   Views:           {result['post']['views']}")
            print(f"   Likes:           {result['post']['likes']}")
            print(f"   Comments:        {result['post']['comments']}")
            if result['post'].get('media_url'):
                print(f"   Media URL:       {result['post']['media_url'][:80]}...")
            if result['post'].get('videoFile'):
                print(f"   Video File:      {result['post']['videoFile'][:80]}...")
            if result['post']['cover_image']:
                print(f"   Cover:           {result['post']['cover_image'][:60]}...")
            print("=" * 55)

            filename = f"{code}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n[SAVED] {filename}")

            return result
        else:
            print(f"[FAIL] Could not scrape {code}")
            return None

def main():
    print("=" * 60)
    print("Eblo.id Scraper v7.1")
    print("=" * 60)
    print("\n1. Bruteforce scrape")
    print("2. Manual scrape")
    print("3. File scrape")
    print("4. Download video")
    print("5. Exit")

    choice = input("\n> ").strip()
    scraper = EbloScraper()

    if choice == '1':
        min_len = input("Min length (default 6): ").strip()
        min_len = int(min_len) if min_len.isdigit() else 6
        max_len = input("Max length (default 7): ").strip()
        max_len = int(max_len) if max_len.isdigit() else 7
        threads = input("Threads (default 20): ").strip()
        threads = int(threads) if threads.isdigit() else 20
        scraper.bruteforce_scrape(min_length=min_len, max_length=max_len, max_threads=threads)
    elif choice == '2':
        url_or_code = input("URL or code: ").strip()
        if url_or_code:
            scraper.custom_scrape(url_or_code)
        else:
            print("[ERROR] Empty input")
    elif choice == '3':
        filepath = input("File path: ").strip()
        if filepath:
            threads = input("Threads (default 20): ").strip()
            threads = int(threads) if threads.isdigit() else 20
            scraper.scrape_from_file(filepath, max_threads=threads)
        else:
            print("[ERROR] Empty input")
    elif choice == '4':
        print("\n[VIDEO DOWNLOAD MODE]")
        print("   Enter post URL or short code")
        print("   Example: https://eblo.id/eWvAkb6 or eWvAkb6")
        url_or_code = input("\n> ").strip()
        if url_or_code:
            scraper.download_from_code(url_or_code)
        else:
            print("[ERROR] Empty input")
    else:
        print("Sosi chlen!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[EXIT]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
