#!/usr/bin/env python3
import re
import json
import requests
import sys
from datetime import datetime

class EbloProfileScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive'
        })

    def scrape_profile(self, username):
        if username.startswith('@'):
            username = username[1:]
        
        url = f"https://eblo.id/@{username}"
        print(f"[FETCH] {url}")
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] Profile not found: {username}")
                return None
            
            html = response.text
            
            profile_login = self._extract_attr(html, 'data-profile-login')
            profile_twitch_id = self._extract_attr(html, 'data-profile-twitch-id')
            profile_7tv = self._extract_attr(html, 'data-7tv-channel')
            is_banned = self._extract_attr(html, 'data-is-banned') == '1'
            
            avatar_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            avatar_url = avatar_match.group(1) if avatar_match else ''
            
            display_name_match = re.search(r'<div class="profile-name"[^>]*data-twitch-id="[^"]*">([^<]+)</div>', html)
            if not display_name_match:
                display_name_match = re.search(r'<div class="username"[^>]*data-twitch-id="[^"]*">([^<]+)</div>', html)
            display_name = display_name_match.group(1).strip() if display_name_match else username
            
            role = 'user'
            if 'moderator' in html.lower() or 'data-is-moderator' in html:
                role = 'moderator'
            elif 'admin' in html.lower() or 'data-is-admin' in html:
                role = 'admin'
            elif is_banned:
                role = 'banned'
            
            is_verified = 'verified' in html.lower() or 'verif' in html.lower()
            
            badge_match = re.search(r'<img[^>]*badge[^>]*alt="([^"]+)"', html)
            badge = badge_match.group(1) if badge_match else None
            
            posts_count_match = re.search(r'(\d+)\s+публикац', html)
            posts_count = int(posts_count_match.group(1)) if posts_count_match else 0
            
            result = {
                "username": username,
                "display_name": display_name,
                "twitch_id": profile_twitch_id if profile_twitch_id else "?",
                "twitch_url": f"https://twitch.tv/{username}" if username else "",
                "7tv_channel_id": profile_7tv if profile_7tv else "?",
                "avatar_url": avatar_url,
                "role": role,
                "is_banned": is_banned,
                "is_verified": is_verified,
                "posts_count": posts_count
            }
            
            if badge:
                result["badge"] = badge
            
            return result
            
        except Exception as e:
            print(f"[ERROR] {e}")
            return None

    def _extract_attr(self, html, attr_name):
        match = re.search(rf'{attr_name}="([^"]+)"', html)
        return match.group(1) if match else None

def main():
    print("=" * 60)
    print("Eblo.id Profile Scraper v3.0")
    print("=" * 60)
    
    username = input("\nEnter username (without @): ").strip()
    if not username:
        print("[ERROR] Empty input")
        sys.exit(1)
    
    scraper = EbloProfileScraper()
    data = scraper.scrape_profile(username)
    
    if not data:
        print("[ERROR] Failed to scrape profile")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("PROFILE RESULT")
    print("=" * 60)
    print(f"   Username:       @{data['username']}")
    print(f"   Display name:   {data['display_name']}")
    print(f"   Twitch ID:      {data['twitch_id']}")
    print(f"   Twitch URL:     {data['twitch_url']}")
    print(f"   7TV ID:         {data['7tv_channel_id']}")
    print(f"   Avatar URL:     {data['avatar_url']}")
    print(f"   Role:           {data['role']}")
    print(f"   Banned:         {data['is_banned']}")
    print(f"   Verified:       {data['is_verified']}")
    if 'badge' in data:
        print(f"   Badge:          {data['badge']}")
    print(f"   Posts:          {data['posts_count']}")
    print("=" * 60)
    
    filename = f"{username}_profile.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVED] {filename}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[EXIT]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
