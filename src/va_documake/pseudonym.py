"""仮名化：登録した語を記号（〔人名Ａ〕など）に置き換え、記号を元の語に戻す（仕様.md の7）。

VA仮名化（VA仮名化\\仕様.md・basDictionary.bas）にそろえる。違う点は次のとおり。
・辞書・対応表はメモリの中だけに持ち、どのファイルにも書かない（このクラスはファイルを読み書きしない）。
・入力欄の文章は実名のまま置き換えず、構文ファイルに書き出すときに記号にする（pseudonymize）。
・一度使った英字は、その文書を開いている間は使い直さない（VA仮名化は、いちばん大きい英字の語を解除すると、
  次に登録した別の語に同じ英字を振る。VA DocuMakeは同じ AI の会話を何往復も続けるので、前の会話の回答の
  記号が、別の人の実名に戻ってしまうのを防ぐ）。
"""
import re
from dataclasses import dataclass

KINDS = ("人名", "法人", "地名", "番号", "その他")
OPEN, CLOSE = "〔", "〕"
MAX_WORD_LENGTH = 100   # 登録できる語の最大文字数（VA仮名化 cstSettings.lngMaxWordLength と同じ）
_WIDE_A, _WIDE_Z = ord("Ａ"), ord("Ｚ")
# 記号（英字が半角になったもの〔人名A〕も同じ記号として見つける）
TOKEN_RE = re.compile("〔(" + "|".join(KINDS) + ")([Ａ-Ｚ]+|[A-Z]+)〕")


def to_wide(text):
    """半角の英大文字を全角にする（〔人名A〕 → 〔人名Ａ〕）。"""
    return "".join(chr(ord(c) + 0xFEE0) if "A" <= c <= "Z" else c for c in text)


def letters_to_number(letters):
    """全角の英字を番号にする（Ａ=1、Ｚ=26、ＡＡ=27）。全角の英字以外を含む・空・6字以上なら 0。"""
    if not letters or len(letters) > 5:
        return 0
    n = 0
    for c in letters:
        if not _WIDE_A <= ord(c) <= _WIDE_Z:
            return 0
        n = n * 26 + ord(c) - _WIDE_A + 1
    return n


def number_to_letters(n):
    """番号を全角の英字にする（1=Ａ、26=Ｚ、27=ＡＡ）。"""
    out = ""
    while n > 0:
        n -= 1
        out = chr(_WIDE_A + n % 26) + out
        n //= 26
    return out


def make_token(kind, n):
    return f"{OPEN}{kind}{number_to_letters(n)}{CLOSE}"


def normalize_token(token):
    """記号の英字を全角にそろえる。"""
    return to_wide(token)


def overlaps_token(word):
    """語が記号の一部になりうるか（VA仮名化 basDictionary.OverlapsToken と同じ判定）。"""
    wide = to_wide(word)
    if OPEN in wide or CLOSE in wide:
        return True
    if letters_to_number(wide) > 0:       # 英字だけ（「Ａ」「ABC」など）
        return True
    for kind in KINDS:
        if wide in kind:                    # 種別の一部（「人名」「名」）
            return True
        for k in range(1, len(kind) + 1):   # 種別の末尾の部分＋英字（「人名Ａ」「名Ａ」）
            if len(wide) > k and wide[:k] == kind[-k:] and letters_to_number(wide[k:]) > 0:
                return True
    return False


def trim_selection(text):
    """選んだ文字列の前後から、改行・空白（半角・全角）を取り除く。"""
    return text.strip(" 　\r\n")


class NotRegistrable(ValueError):
    """登録できない語（理由はメッセージ）。"""


@dataclass
class Entry:
    word: str
    kind: str
    token: str


class Dictionary:
    """1つの文書の辞書・対応表（メモリの中だけ）。"""

    def __init__(self):
        self.entries = {}       # 語 → Entry
        self.used = {k: 0 for k in KINDS}   # 種別ごとに、使ったことのある英字の番号の最大

    # ---------- 登録・解除 ----------

    def check(self, word):
        """登録できるかを確かめ、できなければ NotRegistrable を出す。"""
        if not word:
            raise NotRegistrable("文字を選んでください。")
        if any(ord(c) < 32 for c in word):
            raise NotRegistrable("1つの段落の中で、文字だけを選んでください（改行・タブを含む範囲は仮名化できません）。")
        if len(word) > MAX_WORD_LENGTH:
            raise NotRegistrable(f"選んだ文字列が長すぎます（{MAX_WORD_LENGTH}文字まで）。")
        if overlaps_token(word):
            raise NotRegistrable(f"選んだ文字列は、記号（{OPEN}人名Ａ{CLOSE} など）と重なるため、仮名化できません。")

    def register(self, word, kind):
        """語を登録し、記号を返す。すでに登録されている語なら、その記号を返す。"""
        word = trim_selection(word)
        if kind not in KINDS:
            raise ValueError(kind)
        if word in self.entries:
            return self.entries[word].token
        self.check(word)
        self.used[kind] += 1
        token = make_token(kind, self.used[kind])
        self.entries[word] = Entry(word, kind, token)
        return token

    def add_known(self, word, token):
        """構文ファイルと PDF の突き合わせで求めた対応を加える（記号はそのまま使う）。"""
        m = TOKEN_RE.fullmatch(normalize_token(token))
        if not m:
            raise ValueError(token)
        kind, letters = m.group(1), m.group(2)
        self.entries[word] = Entry(word, kind, normalize_token(token))
        self.used[kind] = max(self.used[kind], letters_to_number(letters))

    def note_used(self, token):
        """構文ファイルにある記号の英字を、使ったことのあるものとして覚える（元の語が分からない記号も）。"""
        m = TOKEN_RE.fullmatch(normalize_token(token))
        if m:
            self.used[m.group(1)] = max(self.used[m.group(1)], letters_to_number(m.group(2)))

    def unregister(self, word_or_token):
        """登録を解除する（語でも記号でもよい）。解除した記号の英字は使い直さない。"""
        key = normalize_token(trim_selection(word_or_token))
        for word, e in list(self.entries.items()):
            if word == key or e.token == key:
                del self.entries[word]
                return e
        return None

    def rename(self, word_or_token, new_word):
        """登録した語の元の語を変え、前の語を返す（記号は変えない。過去の文書・テンプレートを使い回すとき、
        〔人名Ａ〕を前の事件の名前から新しい名前にする。2026-10-25 班長指示）。"""
        e = self.find(word_or_token)
        if e is None:
            raise KeyError(word_or_token)
        new_word = trim_selection(new_word)
        if new_word == e.word:
            return e.word
        if new_word in self.entries:
            raise NotRegistrable(f"「{new_word}」は、すでに {self.entries[new_word].token} として仮名化しています。")
        self.check(new_word)
        old = e.word
        del self.entries[old]
        e.word = new_word
        self.entries[new_word] = e
        return old

    def find(self, word_or_token):
        key = normalize_token(trim_selection(word_or_token))
        for e in self.entries.values():
            if e.word == key or e.token == key:
                return e
        return None

    # ---------- 置き換え ----------

    def pseudonymize(self, text):
        """登録した語を記号に置き換える（長い語から先に置き換える）。"""
        for word in sorted(self.entries, key=len, reverse=True):
            text = text.replace(word, self.entries[word].token)
        return text

    def restore(self, text):
        """記号を元の語に戻し、(戻した文章, 戻せなかった記号のリスト) を返す。英字が半角の記号も戻す。"""
        by_token = {e.token: e.word for e in self.entries.values()}
        unknown = []

        def sub(m):
            token = normalize_token(m.group(0))
            if token in by_token:
                return by_token[token]
            unknown.append(m.group(0))
            return m.group(0)
        return TOKEN_RE.sub(sub, text), unknown

    def spans(self, text):
        """文章の中の登録した語の位置 [(始め, 終わり, Entry)] を返す（入力欄で色を付けるため。長い語を優先し、重ならない）。"""
        taken = [False] * len(text)
        out = []
        for word in sorted(self.entries, key=len, reverse=True):
            start = 0
            while True:
                k = text.find(word, start)
                if k < 0:
                    break
                if not any(taken[k:k + len(word)]):
                    out.append((k, k + len(word), self.entries[word]))
                    for i in range(k, k + len(word)):
                        taken[i] = True
                start = k + 1
        return sorted(out, key=lambda s: s[0])


def tokens_in(text):
    """文章の中の記号を、出てくる順に（英字を全角にそろえて）返す。"""
    return [normalize_token(m.group(0)) for m in TOKEN_RE.finditer(text)]
