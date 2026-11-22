"""Platform metadata shared by the API, recorder engine and file indexer."""
from __future__ import annotations

import re
from urllib.parse import urlparse

QUALITY_OPTIONS = ["原画", "蓝光", "超清", "高清", "标清", "流畅"]

PLATFORMS = [
    dict(code="douyin", name="抖音", hosts=["live.douyin.com", "v.douyin.com", "www.douyin.com"],
         template="https://live.douyin.com/{id}", id_pattern=r"^[A-Za-z0-9_.\-]{2,64}$",
         example="https://live.douyin.com/745964462470", quick="id", dir_name="抖音直播",
         cookie=True, proxy=False),
    dict(code="tiktok", name="TikTok", hosts=["tiktok.com"],
         template="https://www.tiktok.com/@{id}/live", id_pattern=r"^[A-Za-z0-9_.]{2,64}$",
         example="https://www.tiktok.com/@pearlgaga88/live", quick="id", dir_name="TikTok直播",
         cookie=True, proxy=True),
    dict(code="kuaishou", name="快手", hosts=["live.kuaishou.com"],
         template="https://live.kuaishou.com/u/{id}", id_pattern=r"^[A-Za-z0-9_.\-]{2,64}$",
         example="https://live.kuaishou.com/u/yall1102", quick="id", dir_name="快手直播",
         cookie=True, proxy=False),
    dict(code="huya", name="虎牙", hosts=["huya.com"],
         template="https://www.huya.com/{id}", id_pattern=r"^[A-Za-z0-9_\-]{1,64}$",
         example="https://www.huya.com/116", quick="id", dir_name="虎牙直播",
         cookie=True, proxy=False),
    dict(code="douyu", name="斗鱼", hosts=["douyu.com"],
         template="https://www.douyu.com/{id}", id_pattern=r"^[A-Za-z0-9_\-]{1,64}$",
         example="https://www.douyu.com/4921614", quick="id", dir_name="斗鱼直播",
         cookie=True, proxy=False),
    dict(code="yy", name="YY", hosts=["yy.com"],
         template="https://www.yy.com/{id}", id_pattern=r"^\d{4,20}$",
         example="https://www.yy.com/22490906", quick="id", dir_name="YY直播",
         cookie=True, proxy=False),
    dict(code="bilibili", name="B站", hosts=["live.bilibili.com"],
         template="https://live.bilibili.com/{id}", id_pattern=r"^\d{1,20}$",
         example="https://live.bilibili.com/21593109", quick="id", dir_name="B站直播",
         cookie=True, proxy=False),
    dict(code="xhs", name="小红书", hosts=["xiaohongshu.com", "xhslink.com"],
         template=None, id_pattern=None, example="http://xhslink.com/xpJpfM", quick="full_url",
         dir_name="小红书直播", cookie=True, proxy=False),
    dict(code="bigo", name="Bigo", hosts=["bigo.tv", "bigovideo.tv"],
         template="https://www.bigo.tv/cn/{id}", id_pattern=r"^\d{4,20}$",
         example="https://www.bigo.tv/cn/716418802", quick="id", dir_name="Bigo直播",
         cookie=True, proxy=False),
    dict(code="blued", name="Blued", hosts=["app.blued.cn"],
         template=None, id_pattern=None, example="https://app.blued.cn/live?id=Mp6G2R", quick="full_url",
         dir_name="Blued直播", cookie=True, proxy=False),
    dict(code="sooplive", name="SOOP", hosts=["sooplive.co.kr", "sooplive.com"],
         template="https://play.sooplive.co.kr/{id}", id_pattern=r"^[A-Za-z0-9_\-]{2,64}$",
         example="https://play.sooplive.co.kr/sw7love", quick="id", dir_name="SOOP",
         cookie=True, proxy=True),
    dict(code="netease", name="网易CC", hosts=["cc.163.com"],
         template="https://cc.163.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://cc.163.com/583946984", quick="id", dir_name="网易CC直播",
         cookie=True, proxy=False),
    dict(code="qiandurebo", name="千度热播", hosts=["qiandurebo.com"],
         template="https://qiandurebo.com/web/video.php?roomnumber={id}", id_pattern=r"^\d{2,20}$",
         example="https://qiandurebo.com/web/video.php?roomnumber=33333", quick="id", dir_name="千度热播",
         cookie=True, proxy=False),
    dict(code="pandatv", name="PandaTV", hosts=["pandalive.co.kr"],
         template="https://www.pandalive.co.kr/live/play/{id}", id_pattern=r"^[A-Za-z0-9_\-]{2,64}$",
         example="https://www.pandalive.co.kr/live/play/bara0109", quick="id", dir_name="PandaTV",
         cookie=True, proxy=True),
    dict(code="maoerfm", name="猫耳FM", hosts=["fm.missevan.com"],
         template="https://fm.missevan.com/live/{id}", id_pattern=r"^\d{2,20}$",
         example="https://fm.missevan.com/live/868895007", quick="id", dir_name="猫耳FM直播",
         cookie=True, proxy=False),
    dict(code="winktv", name="WinkTV", hosts=["winktv.co.kr"],
         template="https://www.winktv.co.kr/live/play/{id}", id_pattern=r"^[A-Za-z0-9_\-]{2,64}$",
         example="https://www.winktv.co.kr/live/play/anjer1004", quick="id", dir_name="WinkTV",
         cookie=True, proxy=True),
    dict(code="flextv", name="FlexTV", hosts=["flextv.co.kr", "ttinglive.com"],
         template="https://www.flextv.co.kr/channels/{id}/live", id_pattern=r"^[A-Za-z0-9_\-]{2,64}$",
         example="https://www.flextv.co.kr/channels/593127/live", quick="id", dir_name="FlexTV",
         cookie=True, proxy=True),
    dict(code="looklive", name="Look直播", hosts=["look.163.com"],
         template="https://look.163.com/live?id={id}", id_pattern=r"^[A-Za-z0-9_\-]{2,64}$",
         example="https://look.163.com/live?id=65108820", quick="id", dir_name="Look直播",
         cookie=True, proxy=False),
    dict(code="popkontv", name="PopkonTV", hosts=["popkontv.com"],
         template="https://www.popkontv.com/live/view?castId={id}&partnerCode=P-00001",
         id_pattern=r"^[A-Za-z0-9_\-]{2,64}$", example="https://www.popkontv.com/live/view?castId=wjfal007",
         quick="id", dir_name="PopkonTV", cookie=False, proxy=True),
    dict(code="twitcasting", name="TwitCasting", hosts=["twitcasting.tv"],
         template="https://twitcasting.tv/{id}", id_pattern=r"^[A-Za-z0-9_:\-]{2,64}$",
         example="https://twitcasting.tv/c:uonq", quick="id", dir_name="TwitCasting",
         cookie=True, proxy=False),
    dict(code="baidu", name="百度直播", hosts=["live.baidu.com"],
         template=None, id_pattern=None,
         example="https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377",
         quick="full_url", dir_name="百度直播", cookie=True, proxy=False),
    dict(code="weibo", name="微博直播", hosts=["weibo.com"],
         template=None, id_pattern=None, example="https://weibo.com/l/wblive/p/show/1022:2321325026370190442592",
         quick="full_url", dir_name="微博直播", cookie=True, proxy=False),
    dict(code="kugou", name="酷狗直播", hosts=["fanxing.kugou.com", "fanxing2.kugou.com", "mfanxing.kugou.com"],
         template="https://fanxing2.kugou.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://fanxing2.kugou.com/50428671", quick="id", dir_name="酷狗直播",
         cookie=True, proxy=False),
    dict(code="twitch", name="Twitch", hosts=["twitch.tv"],
         template="https://www.twitch.tv/{id}", id_pattern=r"^[A-Za-z0-9_]{2,64}$",
         example="https://www.twitch.tv/gamerbee", quick="id", dir_name="TwitchTV",
         cookie=True, proxy=True),
    dict(code="liveme", name="LiveMe", hosts=["liveme.com"],
         template=None, id_pattern=None, example="https://www.liveme.com/zh/v/17141937295821012854/index.html",
         quick="full_url", dir_name="LiveMe", cookie=True, proxy=True),
    dict(code="huajiao", name="花椒直播", hosts=["huajiao.com"],
         template="https://www.huajiao.com/l/{id}", id_pattern=r"^\d{4,20}$",
         example="https://www.huajiao.com/l/345096174", quick="id", dir_name="花椒直播",
         cookie=True, proxy=False),
    dict(code="liuxing", name="流星直播", hosts=["7u66.com"],
         template="https://www.7u66.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://www.7u66.com/100960", quick="id", dir_name="流星直播",
         cookie=True, proxy=False),
    dict(code="showroom", name="ShowRoom", hosts=["showroom-live.com"],
         template="https://www.showroom-live.com/room/profile?room_id={id}", id_pattern=r"^\d{2,20}$",
         example="https://www.showroom-live.com/room/profile?room_id=511033", quick="id",
         dir_name="ShowRoom", cookie=True, proxy=True),
    dict(code="acfun", name="Acfun", hosts=["live.acfun.cn", "m.acfun.cn"],
         template="https://live.acfun.cn/live/{id}", id_pattern=r"^\d{2,20}$",
         example="https://live.acfun.cn/live/17912421", quick="id", dir_name="Acfun",
         cookie=True, proxy=False),
    dict(code="changliao", name="畅聊直播", hosts=["tlclw.com"],
         template="https://live.tlclw.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://live.tlclw.com/106188", quick="id", dir_name="畅聊直播",
         cookie=True, proxy=False),
    dict(code="yinbo", name="音播直播", hosts=["ybw1666.com"],
         template="https://live.ybw1666.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://live.ybw1666.com/800008687", quick="id", dir_name="音播直播",
         cookie=True, proxy=False),
    dict(code="yingke", name="映客直播", hosts=["inke.cn"],
         template=None, id_pattern=None, example="https://www.inke.cn/liveroom/index.html?uid=710032101",
         quick="full_url", dir_name="映客直播", cookie=True, proxy=False),
    dict(code="zhihu", name="知乎直播", hosts=["zhihu.com"],
         template=None, id_pattern=None, example="https://www.zhihu.com/people/ac3a467005c5d20381a82230101308e9",
         quick="full_url", dir_name="知乎直播", cookie=True, proxy=False),
    dict(code="chzzk", name="CHZZK", hosts=["chzzk.naver.com"],
         template="https://chzzk.naver.com/live/{id}", id_pattern=r"^[A-Za-z0-9]{10,64}$",
         example="https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2", quick="id",
         dir_name="CHZZK", cookie=True, proxy=True),
    dict(code="haixiu", name="嗨秀直播", hosts=["haixiutv.com"],
         template="https://www.haixiutv.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://www.haixiutv.com/6095106", quick="id", dir_name="嗨秀直播",
         cookie=True, proxy=False),
    dict(code="vvxqiu", name="VV星球", hosts=["vvxqiu.com"],
         template=None, id_pattern=None,
         example="https://h5webcdn-pro.vvxqiu.com//activity/videoShare/videoShare.html?roomId=LP115664695",
         quick="full_url", dir_name="VV星球", cookie=True, proxy=False),
    dict(code="17live", name="17Live", hosts=["17.live"],
         template="https://17.live/en/live/{id}", id_pattern=r"^\d{4,20}$",
         example="https://17.live/en/live/6302408", quick="id", dir_name="17Live",
         cookie=True, proxy=False),
    dict(code="langlive", name="浪Live", hosts=["lang.live"],
         template="https://www.lang.live/en-US/room/{id}", id_pattern=r"^\d{4,20}$",
         example="https://www.lang.live/en-US/room/3349463", quick="id", dir_name="浪Live",
         cookie=True, proxy=False),
    dict(code="pplive", name="漂漂直播", hosts=["weimipopo.com"],
         template=None, id_pattern=None,
         example="https://m.pp.weimipopo.com/live/preview.html?uid=91648673&anchorUid=91625862",
         quick="full_url", dir_name="漂漂直播", cookie=True, proxy=False),
    dict(code="6room", name="六间房直播", hosts=["6.cn"],
         template="https://v.6.cn/{id}", id_pattern=r"^\d{2,20}$",
         example="https://v.6.cn/634435", quick="id", dir_name="六间房直播",
         cookie=True, proxy=False),
    dict(code="lehai", name="乐嗨直播", hosts=["lehaitv.com"],
         template="https://www.lehaitv.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://www.lehaitv.com/8059096", quick="id", dir_name="乐嗨直播",
         cookie=True, proxy=False),
    dict(code="huamao", name="花猫直播", hosts=["catshow168.com"],
         template=None, id_pattern=None,
         example="https://h.catshow168.com/live/preview.html?uid=19066357&anchorUid=18895331",
         quick="full_url", dir_name="花猫直播", cookie=True, proxy=False),
    dict(code="shopee", name="Shopee", hosts=["live.shopee.", "shp.ee"],
         template=None, id_pattern=None, example="https://sg.shp.ee/GmpXeuf?uid=1006401066",
         quick="full_url", dir_name="shopee", cookie=True, proxy=True),
    dict(code="youtube", name="YouTube", hosts=["youtube.com", "youtu.be"],
         template=None, id_pattern=None, example="https://www.youtube.com/watch?v=cS6zS5hi1w0",
         quick="full_url", dir_name="Youtube", cookie=True, proxy=True),
    dict(code="taobao", name="淘宝直播", hosts=["tb.cn", "taobao.com"],
         template=None, id_pattern=None, example="https://m.tb.cn/h.TWp0HTd",
         quick="full_url", dir_name="淘宝直播", cookie=True, proxy=False),
    dict(code="jd", name="京东直播", hosts=["3.cn", "jd.com"],
         template=None, id_pattern=None, example="https://3.cn/28MLBy-E",
         quick="full_url", dir_name="京东直播", cookie=True, proxy=False),
    dict(code="faceit", name="Faceit", hosts=["faceit.com"],
         template=None, id_pattern=None, example="https://www.faceit.com/zh/players/Compl1/stream",
         quick="full_url", dir_name="faceit", cookie=True, proxy=True),
    dict(code="migu", name="咪咕直播", hosts=["miguvideo.com"],
         template=None, id_pattern=None, example="https://www.miguvideo.com/p/live/120000541321",
         quick="full_url", dir_name="咪咕直播", cookie=True, proxy=False),
    dict(code="lianjie", name="连接直播", hosts=["lailianjie.com"],
         template="https://show.lailianjie.com/{id}", id_pattern=r"^\d{2,20}$",
         example="https://show.lailianjie.com/10000258", quick="id", dir_name="连接直播",
         cookie=True, proxy=False),
    dict(code="laixiu", name="来秀直播", hosts=["imkktv.com"],
         template=None, id_pattern=None,
         example="https://www.imkktv.com/h5/share/video.html?uid=1845195&roomId=1710496",
         quick="full_url", dir_name="来秀直播", cookie=True, proxy=False),
    dict(code="picarto", name="Picarto", hosts=["picarto.tv"],
         template="https://www.picarto.tv/{id}", id_pattern=r"^[A-Za-z0-9_]{2,64}$",
         example="https://www.picarto.tv/cuteavalanche", quick="id", dir_name="Picarto",
         cookie=True, proxy=True),
    dict(code="custom", name="自定义流", hosts=[], template=None, id_pattern=None,
         example="https://example.com/live/stream.m3u8", quick="full_url", dir_name="自定义录制直播",
         cookie=False, proxy=False),
]

QUALITY_PLATFORMS = {p["code"] for p in PLATFORMS}
DIR_TO_CODE = {p["dir_name"]: p["code"] for p in PLATFORMS}
CODE_TO_NAME = {p["code"]: p["name"] for p in PLATFORMS}
CODE_TO_DIR = {p["code"]: p["dir_name"] for p in PLATFORMS}


def normalize_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    return value


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.endswith("."):
        return host.startswith(pattern)
    if pattern.startswith("."):
        return host.endswith(pattern)
    return host == pattern or host.endswith("." + pattern)


def match_platform(url: str) -> str | None:
    host = host_of(url)
    if not host:
        return None
    for platform in PLATFORMS:
        for pattern in platform["hosts"]:
            if _host_matches(host, pattern):
                return platform["code"]
    lowered = url.lower()
    if ".m3u8" in lowered or ".flv" in lowered:
        return "custom"
    return None


def platform_by_code(code: str) -> dict | None:
    return next((p for p in PLATFORMS if p["code"] == code), None)


def build_url(code: str, platform_id: str) -> str | None:
    platform = platform_by_code(code)
    if not platform or not platform.get("template"):
        return None
    platform_id = (platform_id or "").strip()
    if not platform_id:
        return None
    pattern = platform.get("id_pattern")
    if pattern and not re.fullmatch(pattern, platform_id):
        return None
    return platform["template"].format(id=platform_id)


def validate_platform_url(code: str, url: str) -> bool:
    platform = platform_by_code(code)
    if not platform:
        return False
    if code == "custom":
        lowered = url.lower()
        return lowered.startswith(("http://", "https://")) and (".m3u8" in lowered or ".flv" in lowered)
    matched = match_platform(url)
    return matched == code
