"""
GitHub kmj 브랜치 -> Notion 자동 동기화 스크립트

파일 경로 규칙:
  week{N}/{day}/{파일명}.py
    예시: week1/wed/K번째수.py
           week2/thu/최솟값만들기.py

           day 약어 매핑:
             tue / 화  -> 화요일
               wed / 수  -> 수요일
                 thu / 목  -> 목요일
                   fri / 금  -> 금요일

                   필요한 환경 변수:
                     NOTION_TOKEN            : Notion Integration 시크릿 키
                       NOTION_PARENT_PAGE_ID   : 스터디 메인 페이지 ID
                       """

import os
import sys
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID = os.environ.get(
      "NOTION_PARENT_PAGE_ID", "33db81d1e5aa80209548c04c7b1ea50a"
)
MEMBER_NAME = "김민주"

HEADERS = {
      "Authorization": f"Bearer {NOTION_TOKEN}",
      "Notion-Version": "2022-06-28",
      "Content-Type": "application/json",
}

DAY_MAP = {
      "tue": "화요일", "화": "화요일", "tuesday": "화요일",
      "wed": "수요일", "수": "수요일", "wednesday": "수요일",
      "thu": "목요일", "목": "목요일", "thursday": "목요일",
      "fri": "금요일", "금": "금요일", "friday": "금요일",
}

FRIDAY_KEYWORDS = ["모의 코딩테스트", "모의코딩테스트"]
PROBLEM_KEYWORDS = ["문제 풀이"]


def get_blocks(page_id):
      blocks, cursor = [], None
      while True:
                url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
                if cursor:
                              url += f"&start_cursor={cursor}"
                          res = requests.get(url, headers=HEADERS)
                if res.status_code != 200:
                              print(f"  블록 조회 실패 ({res.status_code}): {res.text[:200]}")
                              break
                          data = res.json()
                blocks.extend(data.get("results", []))
                if not data.get("has_more"):
                              break
                          cursor = data.get("next_cursor")
            return blocks


def search_week_page(week_num):
      url = "https://api.notion.com/v1/search"
    payload = {
              "query": f"{week_num}주차",
              "filter": {"value": "page", "property": "object"},
              "page_size": 10,
}
            res = requests.post(url, headers=HEADERS, json=payload)
    if res.status_code != 200:
              print(f"  검색 실패 ({res.status_code}): {res.text[:200]}")
              return None

    for result in res.json().get("results", []):
              title = "".join(
                            t.get("plain_text", "")
                            for t in result.get("properties", {}).get("title", {}).get("title", [])
              )
              if f"{week_num}주차" in title:
                            print(f"  {week_num}주차 페이지 발견: {title} ({result['id']})")
                    return result["id"]
    return None


                                                def find_code_block(page_id, day_korean):
                      blocks = get_blocks(page_id)
                                                      in_day_section = False
    in_member_section = False

    for block in blocks:
              btype = block["type"]

        if btype == "heading_2":
                      text = "".join(
                          t.get("plain_text", "")
                          for t in block["heading_2"].get("rich_text", [])
)
            all_kw = FRIDAY_KEYWORDS + PROBLEM_KEYWORDS
            if day_korean in text and any(kw in text for kw in all_kw):
                              in_day_section = True
                        in_member_section = False
                print(f"  섹션 진입: {text.strip()}")
                continue
            if in_day_section:
                              in_day_section = False
                              in_member_section = False

        if in_day_section and btype == "heading_3":
                      text = "".join(
                          t.get("plain_text", "")
                          for t in block["heading_3"].get("rich_text", [])
)
            if MEMBER_NAME in text:
                              in_member_section = True
                              print(f"  멤버 섹션 진입: {text.strip()}")
else:
                in_member_section = False

        if in_day_section and in_member_section and btype == "code":
                      print(f"  코드 블록 발견: {block['id']}")
            return block["id"]

    return None


def update_code_block(block_id, code, language="python"):
      url = f"https://api.notion.com/v1/blocks/{block_id}"
    chunks = [code[i:i+2000] for i in range(0, len(code), 2000)]
    rich_text = [{"type": "text", "text": {"content": c}} for c in chunks]
    payload = {"code": {"rich_text": rich_text, "language": language}}
    res = requests.patch(url, headers=HEADERS, json=payload)
    if res.status_code == 200:
              return True
    print(f"  코드 블록 업데이트 실패 ({res.status_code}): {res.text[:300]}")
    return False


def parse_path(file_path):
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) < 3:
        return None, None
    week_part = parts[0].lower()
    day_part = parts[1].lower()
    week_num = None
    if week_part.startswith("week"):
              try:
                            week_num = int(week_part[4:])
except ValueError:
            pass
elif week_part.endswith("주차"):
        try:
                      week_num = int(week_part[:-2])
except ValueError:
            pass
    day_korean = DAY_MAP.get(day_part)
    return week_num, day_korean


def sync_file(file_path):
              print(f"\n동기화 시작: {file_path}")
    if not os.path.exists(file_path):
              print(f"  파일 없음 (삭제된 파일일 수 있음): {file_path}")
        return False
    week_num, day_korean = parse_path(file_path)
    if week_num is None or day_korean is None:
        print(f"  경로 파싱 실패. 규칙: week{{N}}/{{day}}/{{파일명}}.py")
        return False
    print(f"  {week_num}주차 / {day_korean}")
    with open(file_path, "r", encoding="utf-8") as f:
              code = f.read().strip()
    if not code:
                  print("  파일 내용이 비어 있음")
              return False
    page_id = search_week_page(week_num)
    if not page_id:
              print(f"  Notion에서 {week_num}주차 페이지를 찾을 수 없음")
        return False
    code_block_id = find_code_block(page_id, day_korean)
    if not code_block_id:
                        print(f"  {day_korean} 섹션의 {MEMBER_NAME} 코드 블록을 찾을 수 없음")
              return False
    if update_code_block(code_block_id, code):
              print(f"  Notion 업데이트 완료!")
        return True
    return False


def main():
      if len(sys.argv) < 2:
                print("Usage: python sync_to_notion.py <changed_files.txt>")
                sys.exit(1)
            if not NOTION_TOKEN:
                      print("NOTION_TOKEN 환경 변수가 설정되지 않음")
                      sys.exit(1)
                    with open(sys.argv[1], "r", encoding="utf-8") as f:
                              files = [line.strip() for line in f if line.strip().endswith(".py")]
                          if not files:
                                    print("동기화할 .py 파일이 없습니다.")
                                    sys.exit(0)
                                print(f"동기화 대상 파일 {len(files)}개:")
    for fp in files:
              print(f"   - {fp}")
    success = sum(1 for fp in files if sync_file(fp))
    print(f"\n완료: {success}/{len(files)} 파일 동기화 성공")
    if success < len(files):
              sys.exit(1)


if __name__ == "__main__":
      main()
