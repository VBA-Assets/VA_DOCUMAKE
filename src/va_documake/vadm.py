"""構文ファイル（.vadm）の書き出し・読み込みと、AI の回答を取り込む前の確かめ（仕様.md の8）。

・中身は、AI への指示、区切りの行（文書ID・版・設定）、記号に置き換えた文書の3つ（UTF-8）。
・実名・文書の名前・フォルダのパスは書かない。ファイル名は「<文書ID>.vadm」とする。
・AI の回答は、区切りの行から下を1つのコードブロックで返させる。読み込むときは、区切りの行より上
  （AI への指示、AI の前置き）と、コードブロックの閉じの記号から下（AI の結び）を捨てる。
・AI の画面が回答に混ぜる内部の目印の行（「<?thinking_complete?>」だけの行）は、読み込むときに除く（Content.dropped）。
"""
import difflib
import hashlib
import os
import re
import secrets
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .doctypes import DOC_TYPES, PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_LABELS
from .document import (INDENT_MARK, cell_align_mark, is_line_mark, move_wraps_after_marks, parse_separator, split_cells,
                       split_lead_marks)
from .pseudonym import tokens_in

EXTENSION = ".vadm"
# 文書ID：8字。見間違えやすい字（0・O・1・I）は使わない
DOC_ID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DOC_ID_LENGTH = 8
SEPARATOR_RE = re.compile(r"^\s*={2,}\s*VA\s*DocuMake\s+文書ID\s+([0-9A-Z]+)\s+版\s+(\d+)(.*?)\s*={2,}\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
# AI の画面が回答のコードブロックに混ぜる、内部の目印の行（2026-10-25 の往復試験で claude.ai が「<?thinking_complete?>」を
# 混ぜた）。取り込むときに除き、除いたことを知らせる（2026-10-25 班長決定）
AI_MARKER_RE = re.compile(r"^\s*<\?[A-Za-z_][\w:.-]*\?>\s*$")


PROMPT = """このファイルは、ツール「VA DocuMake」の構文ファイル（AI に渡すために、実名を記号に置き換えたもの）です。「==== VA DocuMake」で始まる区切りの行より上は AI への指示、下は編集する文書です。

1　状況
私は、法律事務所などで使う文書を、ツール「VA DocuMake」で作っている。VA DocuMakeは、区切りの行より下のマークダウンを読み込み、見出しの番号・インデント・配置を自動で付けて、裁判所提出書類などの書式の PDF に組む。
依頼者などの実名を AI に渡さないため、人名・法人名・地名・番号などは、〔人名Ａ〕〔法人Ａ〕〔地名Ａ〕〔番号Ａ〕〔その他Ａ〕のような記号に置き換えてある。同じ記号は、文書のどこでも同じ語を表す。VA DocuMakeは、あなたの回答を取り込むときに、記号を文字どおりに探して元の語に戻す。記号が少しでも変わると（括弧が［］や()に変わる、英字が変わる、「同人」「同社」に言い換えられる）、その部分は元に戻らない。
行の先頭の「:=: 」は表題、「:-: 」は中央揃え、「--: 」は右揃え、「:-- 」は左揃えの記号（マークダウンの表の区切りの行と同じく、コロンのある側に寄せる。記号の後に半角空白を1つ置く）、「-> 」は段落の1行目を1字下げる記号（見出しの後に使うと、そこから先は見出しの番号・インデントを付けない）、「+2 」は段落の左インデントを全角2字にする記号（数字が字数）、「[HEADER] 」はその行をヘッダー（文書の最初のページと、セクション区切りの直後のページの上の余白。「別紙」などを書く）に、「[FOOTER] 」はフッター（各ページの下の余白）に出す記号（配置の記号と一緒に使うことがある）である。表のセルの先頭の「:-: 」「--: 」「:-- 」も、そのセルの配置の記号である。その行だけを書いた <<< は改ページ、<<<= はセクション区切り（改ページして見出しの番号を振り直す）、[TOC] は目次を組む位置の記号である（[TOC:2] のように、載せる見出しの段を書き添えることがある）。**語** は太字（ゴシック体）の記号、*語* は傍点（字の上の点）の記号、[語]{5} は語を5字の幅に均等に割り付ける記号、==語== は私が画面で付けた目印（蛍光ペン。PDF には出ない）である。空の行は、そのまま1行の空きになる。VA DocuMakeは、この記号で表題・中央揃え・右揃え・改ページなどを決める。記号が消えると、配置が失われる。
区切りの行には、文書ID・版と、文書の種類などの設定が書いてある。VA DocuMakeは、回答の最初の行にある区切りの行で、どの文書のどの版をもとにした回答かを確かめる。区切りの行がないと、回答を取り込めない。

2　任務
VA DocuMakeに取り込ませるだけで、実名に戻った文書が正しい書式で出来上がるよう、記号・配置の記号・区切りの行を一字も変えずに残したまま、私の依頼に応えよ。

3　実行
必ず達成すること：
・記号（〔人名Ａ〕など）は、括弧と英字を含めて一字も変えずに書く。言い換えない。新しい記号を作らない。記号の中身を推測しない。
・配置の記号（:=: :-: --: :-- -> +2 など）と、ヘッダー・フッターの記号（[HEADER] [FOOTER]）、改ページの記号（<<< <<<=）、目次の記号（[TOC] [TOC:2] など）は、元の行にそのまま残す（記号の後の半角空白も残す）。新しく付けるのは、私が求めたときだけとする。
・空行を入れない。元の文書にある空の行は、そのまま残す（空の行は、PDF で1行の空きになる）。
・見出しは # の数で階層を表す（# が第１、## が１、### が(1)…）。見出しに番号を書かない。# だけの行のすぐ後に見出しを書くと、2つの見出しを1行にまとめる（「第１　１　当事者」。複合見出し）。表題・日付・宛先など、最初の見出しより前の行には # を付けない。
・表は、| で列を区切るマークダウンの表で書く。2行目の - = : や、セルの先頭の配置の記号は、私が求めたときを除き、変えない。見出しの行の下を2重線にするときは、2行目のすべての列の - を = にする（|===|===|）。
・太字は **語**、傍点は *語* で書く（太字と傍点を重ねると ***語***）。元の文書の太字・傍点の記号は残し、新しく付けるのは、私が求めたときだけとする。蛍光ペンの記号（==語==）と均等割付の記号（[語]{5}）は、私が求めたときを除き、付け外ししない。斜体・水平線・引用・リンク・HTML タグを使わない。1つの段落は1行に書き、段落の途中で改行しない。
・依頼が文書の書き直しである場合は、依頼した箇所以外の文字を変えない（要約・言い換えをしない）。
最終状態：回答を VA DocuMakeに取り込むと、記号がすべて実名に戻り、配置と見出しの階層が元の文書と同じに保たれている。

4　使えるもの・制約
・記号の後に「さん」「様」などを付けるのは構わない。
・このファイルと同じフォルダにあるほかの構文ファイル（.vadm）は、別の事件の文書である。開いたり、内容を参考にしたりしない（記号は文書ごとに別の語を表す）。
・記号の扱いについて確かめたいことがあれば、回答する前に質問せよ。

5　成果物・報告
・文書を書き直したときは、区切りの行から文書の最後までの全体を、1つのコードブロックに入れて出力せよ。コードブロックの最初の行は、区切りの行を一字も変えずに書く。この指示の部分は出力しない。コードブロックの前後の説明は短くする。
・文書の全体を出力する前に、区切りの行・記号・配置の記号が、元の文書と同じ形で残っているかを確かめよ。
"""


# 前の版の既定の AI への指示（rstrip した文字列の SHA-256）。これと同じ指示の構文ファイルを開いたときは、利用者が
# 直した指示ではなく既定の指示として扱い、今の版の指示に替える（記号を足したときに、新しい記号の説明が届くように）
PREVIOUS_PROMPTS = {
    "0ce85b4c666bb7878cb10d84780f683fcb7568700df109696066e1a23c551fa0",    # Ver130（[HEADER] [FOOTER] の前）
}


def is_default_prompt(prompt):
    """prompt（構文ファイル・オプションの画面の指示）が、今の版か前の版の既定の指示か。"""
    text = prompt.rstrip()
    return text == PROMPT.rstrip() or hashlib.sha256(text.encode("utf-8")).hexdigest() in PREVIOUS_PROMPTS


class NoSeparator(ValueError):
    """区切りの行（文書ID・版）が見つからない。"""


class OtherDocument(ValueError):
    """開いている文書と、文書ID が違う。"""


@dataclass
class Settings:
    doc_type: str = "Saiban"                     # DOC_TYPES のキー
    page_number: str = PAGE_NUMBER_BOTTOM_CENTER  # PAGE_NUMBER_* のいずれか
    line_numbers: bool = False                   # 行番号を付けるか（2026-10-24 班長指示）


@dataclass
class Content:
    doc_id: str
    version: int
    settings: Settings = None     # 区切りの行に設定がなければ None
    body: list = field(default_factory=list)   # 文書の行（記号入り）
    prompt: str = None            # AI への指示の部分（なければ None。AI の回答で上書きしたファイルなど）
    dropped: list = field(default_factory=list)   # 除いた AI の内部の目印の行（「<?thinking_complete?>」など）

    @property
    def body_text(self):
        return "\n".join(self.body)


def new_doc_id():
    return "".join(secrets.choice(DOC_ID_CHARS) for _ in range(DOC_ID_LENGTH))


def file_name(doc_id):
    return doc_id + EXTENSION


def default_folder():
    """構文ファイルだけを置く決まったフォルダ（ドキュメント\\VA DocuMake\\構文ファイル。2026-10-24 に「構文ファイル」から
    改めた。設定に保存場所が書いてあれば、そちらを使う）。"""
    docs = None
    if os.name == "nt":
        # ドキュメントのフォルダは OneDrive などに移されていることがあるので、Windows に尋ねる
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:   # 5 = CSIDL_PERSONAL
            docs = Path(buf.value)
    if docs is None:
        docs = Path.home() / "Documents"
    return docs / "VA DocuMake" / "構文ファイル"


# ---------- 区切りの行 ----------

def separator_line(doc_id, version, settings):
    dt = DOC_TYPES[settings.doc_type]
    return (f"==== VA DocuMake 文書ID {doc_id} 版 {version} "
            f"種類 {dt.label} ページ番号 {PAGE_NUMBER_LABELS[settings.page_number]} "
            f"行番号 {'あり' if settings.line_numbers else 'なし'} ====")


def parse_separator(line):
    """区切りの行なら (文書ID, 版, 設定〔なければ None〕) を、そうでなければ None を返す。"""
    m = SEPARATOR_RE.match(line)
    if not m:
        return None
    words = m.group(3).split()
    pairs = dict(zip(words[0::2], words[1::2]))
    settings = None
    by_label = {d.label: d.key for d in DOC_TYPES.values()}
    if pairs.get("種類") in by_label:
        page = {v: k for k, v in PAGE_NUMBER_LABELS.items()}.get(pairs.get("ページ番号"), PAGE_NUMBER_BOTTOM_CENTER)
        # 行番号の書いていない区切りの行（2026-10-24 より前の構文ファイル）は「なし」
        settings = Settings(by_label[pairs["種類"]], page, pairs.get("行番号") == "あり")
    return m.group(1), int(m.group(2)), settings


# ---------- 書き出し・読み込み ----------

def build(doc_id, version, settings, body, prompt=None):
    """構文ファイルの中身を作る。body は記号に置き換えた文書（文字列）。

    prompt は AI への指示の部分。利用者が構文ファイルの指示を書き換えていれば、それを渡す
    （構文ファイルは、AI に渡す前も後も自由に直してよい。2026-10-23 班長指示）。None なら既定の指示。
    """
    lines = body.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    head = (prompt if prompt is not None else PROMPT).rstrip()
    return head + "\n\n" + separator_line(doc_id, version, settings) + "\n" + "\n".join(lines) + "\n"


def is_prompt(lines):
    """区切りの行より上が、AI への指示の部分か（AI の回答の前置きではないか）。

    VA DocuMakeが書いた指示の書き出しか、班長の指示文の型の「1　状況」があれば、指示とみなす。
    利用者がそのどちらも消した場合は、AI の前置きとして捨て、保存するときに既定の指示を書く。
    """
    text = "\n".join(lines)
    return "ツール「VA DocuMake」" in text or "1　状況" in text


def parse_text(text):
    """構文ファイル・AI の回答を読み、Content を返す。区切りの行がなければ NoSeparator を出す。"""
    lines = text.lstrip("﻿").splitlines()
    at = next((k for k, ln in enumerate(lines) if SEPARATOR_RE.match(ln)), None)
    if at is None:
        raise NoSeparator("区切りの行（「==== VA DocuMake 文書ID …」の行）が見つかりません。")
    doc_id, version, settings = parse_separator(lines[at])
    body, dropped = [], []
    for ln in lines[at + 1:]:
        if FENCE_RE.match(ln):    # コードブロックの閉じの記号。ここから下は AI の結びの文
            break
        if AI_MARKER_RE.match(ln):
            dropped.append(ln.strip())
            continue
        body.append(ln.rstrip())
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    prompt = "\n".join(lines[:at]).rstrip() + "\n" if is_prompt(lines[:at]) else None
    return Content(doc_id, version, settings, body, prompt, dropped)


def read_file(path):
    with open(path, encoding="utf-8-sig") as f:
        return parse_text(f.read())


def write_file(path, text):
    """書き出す（一時ファイルに書いてから置き換える。途中で止まっても、前の版が壊れないように）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=EXTENSION, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------- 取り込む前の確かめ（仕様.md の8.3） ----------

@dataclass
class Review:
    older: bool = False          # 今の版より前の版をもとにした回答か
    newer: bool = False          # 今の版より後の版（ふつうは起きない）
    unknown_tokens: list = field(default_factory=list)   # 登録していない記号
    lost_tokens: list = field(default_factory=list)      # 今の文章にあって、回答で消えた記号
    lost_marks: list = field(default_factory=list)       # 消えた配置などの記号 [(記号, 今の文章の行)]
    changes: list = field(default_factory=list)          # [(種類, 今の行のリスト, 回答の行のリスト)]。種類は 変更・削除・追加
    changed_lines: list = field(default_factory=list)    # 回答で変わった・増えた行（回答の文書の何行目か。0 から）
    removed: list = field(default_factory=list)          # 回答で消えた段落（今の文章の行。変わったのではなく、なくなったもの）

    @property
    def clean(self):
        return not (self.older or self.newer or self.unknown_tokens or self.lost_tokens or self.lost_marks)


def _marks(lines):
    out = []
    for ln in lines:
        s = ln.strip()
        if is_line_mark(s):
            out.append((s, ln))
            continue
        if s.startswith("|"):
            # 表のセルの配置の記号（区切りの行の : は比べない）
            if parse_separator(s) is None:
                out += [(m.strip(), ln) for m in map(cell_align_mark, split_cells(s)) if m]
            continue
        lead = split_lead_marks(move_wraps_after_marks(ln))
        if lead.left:
            out.append(("+N", ln))     # 字数は比べない（直してよい）
        # ヘッダー・フッターの記号は、大文字・小文字を比べない
        for m in (lead.align, INDENT_MARK if lead.first else "", lead.area.upper()):
            if m:
                out.append((m.strip(), ln))
    return out


def review(content, doc_id, version, current_body, dictionary):
    """AI の回答（content）を、今の文章（current_body：記号入りの行のリスト）と比べる。

    文書ID が違えば OtherDocument を出す（取り込む前に止める）。版の違いは止めずに知らせる
    （AI は会話の途中、最初に渡された版の番号を書き続けるため。2026-10-23 の往復試験）。
    """
    if content.doc_id != doc_id:
        raise OtherDocument(f"この回答は、別の文書（文書ID {content.doc_id}）のものです。開いている文書の文書ID は {doc_id} です。")
    r = Review(older=content.version < version, newer=content.version > version)
    new_tokens = tokens_in(content.body_text)
    old_tokens = tokens_in("\n".join(current_body))
    r.unknown_tokens = [t for t in dict.fromkeys(new_tokens) if dictionary.find(t) is None]
    r.lost_tokens = [t for t in dict.fromkeys(old_tokens) if t not in new_tokens]
    new_marks = Counter(m for m, _ in _marks(content.body))
    seen = Counter()
    for m, ln in _marks(current_body):
        seen[m] += 1
        if seen[m] > new_marks[m]:
            r.lost_marks.append((m, ln))
    # 空の行も比べる（空の行は1行の空きになるので、AI が足した・消した空行も変更として示す。2026-10-23）。
    # ただし、文書の初めと終わりの空の行は、読み込みで取り除くので比べない
    old = list(current_body)
    while old and not old[-1].strip():
        old.pop()
    while old and not old[0].strip():
        old.pop(0)
    new_index = list(range(len(content.body)))
    new = list(content.body)
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    names = {"replace": "変更", "delete": "削除", "insert": "追加"}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            r.changes.append((names[tag], old[i1:i2], new[j1:j2]))
            r.changed_lines.extend(new_index[j1:j2])
            if tag == "delete":
                r.removed.extend(ln for ln in old[i1:i2] if ln.strip())
    return r
