#!/usr/bin/env python3

import re
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timezone


# ==========================================================
# 5 个规则源
# ==========================================================

SOURCES = [
    {
        "name": "5whys",
        "url": "https://raw.githubusercontent.com/5-whys/adh-rules/main/rules/output_super_domains.txt",
    },
    {
        "name": "adguard",
        "url": "https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt",
    },
    {
        "name": "youtube",
        "url": "https://raw.githubusercontent.com/kboghdady/youTube_ads_4_pi-hole/refs/heads/master/youtubelist.txt",
    },
    {
        "name": "adrules",
        "url": "https://gp.adrules.top/mosdns_adrules.txt",
    },
    {
        "name": "antiad",
        "url": "https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-domains.txt",
    },
]


# ==========================================================
# 输出目录
# ==========================================================

OUTPUT_DIR = Path("output")
SOURCE_DIR = OUTPUT_DIR / "sources"

RULES_FILE = OUTPUT_DIR / "rules.txt"
YOUTUBE_FILE = OUTPUT_DIR / "youtube_ads_domains.txt"
META_FILE = OUTPUT_DIR / "meta.json"


# ==========================================================
# 不拦截的核心域名
#
# 注意：
# 不加入 googlevideo.com
#
# 防止误伤 YouTube 视频流
# ==========================================================

CORE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "youtubei.googleapis.com",
    "ytimg.com",
    "i.ytimg.com",
    "googleapis.com",
    "gstatic.com",
}


# ==========================================================
# 域名验证
# ==========================================================

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9]"
    r"(?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"\.)+"
    r"[a-z]{2,63}$",
    re.IGNORECASE,
)


def is_valid_domain(domain):
    domain = domain.lower().rstrip(".")

    if not domain:
        return False

    if len(domain) > 253:
        return False

    if ".." in domain:
        return False

    if not DOMAIN_RE.match(domain):
        return False

    if domain.endswith(".local"):
        return False

    return True


# ==========================================================
# 是否属于核心域名
# ==========================================================

def is_core_domain(domain):
    domain = domain.lower().rstrip(".")

    for core in CORE_DOMAINS:

        if domain == core:
            return True

        if domain.endswith("." + core):
            return True

    return False


# ==========================================================
# 提取域名
# ==========================================================

def extract_domain(line):
    line = line.strip()

    if not line:
        return None

    # BOM
    line = line.lstrip("\ufeff")

    # ------------------------------------------------------
    # 注释
    # ------------------------------------------------------

    if line.startswith("#"):
        return None

    if line.startswith("!"):
        return None

    # ------------------------------------------------------
    # AdGuard 白名单
    #
    # @@||example.com^
    #
    # 必须完全跳过
    # ------------------------------------------------------

    if line.startswith("@@"):
        return None

    # ------------------------------------------------------
    # AdGuard cosmetic
    # ------------------------------------------------------

    if "##" in line:
        return None

    if "#@#" in line:
        return None

    if "#?#" in line:
        return None

    # ------------------------------------------------------
    # AdGuard modifier
    # ------------------------------------------------------

    if "$" in line:
        line = line.split("$", 1)[0]

    # ------------------------------------------------------
    # MOSDNS / AdRules
    #
    # domain:example.com
    # ------------------------------------------------------

    if line.lower().startswith("domain:"):
        line = line[7:].strip()

    # ------------------------------------------------------
    # hosts 格式
    #
    # 0.0.0.0 example.com
    # 127.0.0.1 example.com
    # ::1 example.com
    # ------------------------------------------------------

    parts = line.split()

    if len(parts) >= 2:

        first = parts[0].lower()

        if first in {
            "0.0.0.0",
            "127.0.0.1",
            "127.0.0.2",
            "::",
            "::1",
        }:
            line = parts[1]

    # ------------------------------------------------------
    # AdGuard
    #
    # ||example.com^
    # ------------------------------------------------------

    if line.startswith("||"):

        line = line[2:]

        line = re.split(
            r"[/^$]",
            line,
            maxsplit=1
        )[0]

    # ------------------------------------------------------
    # URL
    # ------------------------------------------------------

    if "://" in line:

        try:
            parsed = urlparse(line)

            if parsed.hostname:
                line = parsed.hostname
            else:
                return None

        except Exception:
            return None

    # ------------------------------------------------------
    # 清理
    # ------------------------------------------------------

    line = line.strip()

    line = line.strip("|")

    line = line.strip()

    # 通配符
    line = line.lstrip("*.")

    # 端口
    if line.count(":") == 1:

        host, port = line.rsplit(":", 1)

        if port.isdigit():
            line = host

    # IPv4
    if re.fullmatch(
        r"\d{1,3}(?:\.\d{1,3}){3}",
        line
    ):
        return None

    # IPv6
    if ":" in line:
        return None

    # 小写
    line = line.lower()

    # 去末尾点
    line = line.rstrip(".")

    # ------------------------------------------------------
    # 验证
    # ------------------------------------------------------

    if not is_valid_domain(line):
        return None

    # ------------------------------------------------------
    # 核心域名排除
    # ------------------------------------------------------

    if is_core_domain(line):
        return None

    return line


# ==========================================================
# 下载
# ==========================================================

def download(url, path):

    print()
    print("=" * 70)
    print("DOWNLOAD")
    print(url)
    print("=" * 70)

    request = Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "(compatible; "
                "MOSDNS-Rules-Updater/1.0)"
        },
    )

    with urlopen(
        request,
        timeout=180
    ) as response:

        data = response.read()

    if not data:
        raise RuntimeError(
            "Downloaded file is empty"
        )

    path.write_bytes(data)

    print(
        f"Downloaded: "
        f"{len(data) / 1024 / 1024:.2f} MiB"
    )


# ==========================================================
# 解析
# ==========================================================

def parse_source(name, path):

    print()
    print("=" * 70)
    print("PARSE")
    print(name)
    print("=" * 70)

    domains = set()

    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    for line in text.splitlines():

        domain = extract_domain(line)

        if domain:
            domains.add(domain)

    print(
        f"{name}: "
        f"{len(domains):,} domains"
    )

    return domains


# ==========================================================
# 写排序后的域名
# ==========================================================

def write_sorted(path, domains):

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:

        for domain in sorted(domains):
            f.write(domain + "\n")


# ==========================================================
# 主程序
# ==========================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_domains = set()

    youtube_domains = set()

    source_stats = {}

    # ======================================================
    # 下载 + 解析 5 个源
    # ======================================================

    for source in SOURCES:

        name = source["name"]
        url = source["url"]

        source_file = (
            SOURCE_DIR /
            f"{name}.txt"
        )

        # --------------------------------------------------
        # 下载失败直接退出
        #
        # 不允许生成不完整规则
        # --------------------------------------------------

        try:

            download(
                url,
                source_file
            )

        except Exception as error:

            print()
            print(
                f"ERROR downloading "
                f"{name}:"
            )

            print(error)

            sys.exit(1)

        # --------------------------------------------------
        # 解析
        # --------------------------------------------------

        try:

            domains = parse_source(
                name,
                source_file
            )

        except Exception as error:

            print()
            print(
                f"ERROR parsing "
                f"{name}:"
            )

            print(error)

            sys.exit(1)

        # --------------------------------------------------
        # 防止源异常返回网页/错误页面
        # 导致最终规则为空
        # --------------------------------------------------

        if len(domains) == 0:

            print(
                f"ERROR: {name} "
                f"contains 0 valid domains"
            )

            sys.exit(1)

        source_stats[name] = {
            "status": "ok",
            "domains": len(domains),
            "url": url,
        }

        all_domains.update(domains)

        # --------------------------------------------------
        # YouTube 单独保存
        # --------------------------------------------------

        if name == "youtube":

            youtube_domains.update(
                domains
            )

    # ======================================================
    # 最终再次过滤核心域名
    # ======================================================

    all_domains = {
        domain
        for domain in all_domains
        if not is_core_domain(domain)
    }

    youtube_domains = {
        domain
        for domain in youtube_domains
        if not is_core_domain(domain)
    }

    # ======================================================
    # 安全检查
    # ======================================================

    if len(all_domains) == 0:

        print(
            "ERROR: final rules contain "
            "0 domains"
        )

        sys.exit(1)

    # ======================================================
    # 写 rules.txt
    # ======================================================

    write_sorted(
        RULES_FILE,
        all_domains
    )

    # ======================================================
    # 写 YouTube 专用规则
    # ======================================================

    write_sorted(
        YOUTUBE_FILE,
        youtube_domains
    )

    # ======================================================
    # 文件大小
    # ======================================================

    rules_size = (
        RULES_FILE.stat().st_size
    )

    youtube_size = (
        YOUTUBE_FILE.stat().st_size
    )

    # ======================================================
    # Meta
    # ======================================================

    now = datetime.now(
        timezone.utc
    ).isoformat()

    meta = {
        "generated_at": now,

        "source_count":
            len(SOURCES),

        "total_domains":
            len(all_domains),

        "youtube_domains":
            len(youtube_domains),

        "rules_bytes":
            rules_size,

        "rules_mib":
            round(
                rules_size /
                1024 /
                1024,
                2
            ),

        "youtube_bytes":
            youtube_size,

        "youtube_mib":
            round(
                youtube_size /
                1024 /
                1024,
                2
            ),

        "sources":
            source_stats,

        "core_domains_excluded":
            sorted(
                CORE_DOMAINS
            ),
    }

    META_FILE.write_text(
        json.dumps(
            meta,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ======================================================
    # 最终输出
    # ======================================================

    print()
    print()
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    print(
        f"TOTAL DOMAINS : "
        f"{len(all_domains):,}"
    )

    print(
        f"RULES SIZE    : "
        f"{rules_size / 1024 / 1024:.2f} MiB"
    )

    print(
        f"YOUTUBE DOMAINS: "
        f"{len(youtube_domains):,}"
    )

    print(
        f"YOUTUBE SIZE  : "
        f"{youtube_size / 1024 / 1024:.2f} MiB"
    )

    print()
    print("Sources:")

    for name, info in source_stats.items():

        print(
            f"  {name:10s} "
            f"{info['domains']:,}"
        )

    print()
    print("Core domains excluded:")

    for domain in sorted(
        CORE_DOMAINS
    ):
        print(
            f"  {domain}"
        )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
