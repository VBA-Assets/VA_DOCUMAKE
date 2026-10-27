"""仮名化：登録した語を記号（〔人名Ａ〕など）に置き換え、記号を元の語に戻す（仕様.md の7）。

VA仮名化（VA仮名化\\仕様.md・basDictionary.bas）にそろえる。違う点は次のとおり。
・辞書・対応表はメモリの中だけに持ち、どのファイルにも書かない（このクラスはファイルを読み書きしない）。
・エディターは常に記号で表示する（2026-10-24 班長決定）。エディターに入れる文章・打った語・貼った語を記号にし
  （pseudonymize）、確認表示・PDF に組むときに元の語に戻す（restore）。
・解除した記号を別の語に付けるときは、確かめる（VA Documentは同じ AI の会話を何往復も続けるので、前の回答に
  残っている記号が、別の人の実名に戻ってしまうことがある。reuse_warning。2026-10-25 班長決定。それまでは、
  一度使った英字は使い直さなかった〔2026-10-23 班長決定〕）。同じ語に付け直すのは、確かめない。
・記号の字（英字・数字・漢字など）は、画面では利用者が必ず選ぶ（自動では振らない。「依頼者はＡから、相手方はＸから」のように、文書を
  またいで同じ人に同じ記号を付けられるように。2026-10-25 班長決定）。register の letters を省くと、その文書で
  まだ使っていない、いちばん小さい英字を振る（試験などで使う）。
"""
import re
from dataclasses import dataclass

KINDS = ("人名", "法人", "地名", "番号", "その他")
OPEN, CLOSE = "〔", "〕"
MAX_WORD_LENGTH = 100   # 登録できる語の最大文字数（VA仮名化 cstSettings.lngMaxWordLength と同じ）
_WIDE_A, _WIDE_Z = ord("Ａ"), ord("Ｚ")
# 記号：〔種別＋記号の字〕。記号の字は、利用者が打つ文字と数字（英字・数字・漢字・かななど。字数の制限なし。
# 2026-10-25 班長指示。それまでは英字だけ）。空白・括弧・マークダウンの記号（* = | [ ] など）は使えない
# （[^\W_] は、文字と数字。下線は除く）。英字・数字が半角のもの（〔人名A〕〔人名1〕）も同じ記号として見つける
TOKEN_RE = re.compile("〔(" + "|".join(KINDS) + r")([^\W_]+)〕")
_LABEL_RE = re.compile(r"[^\W_]+")


def to_wide(text):
    """半角の英字・数字を全角にし、英字は大文字にそろえる（〔人名a〕〔人名A〕 → 〔人名Ａ〕、〔人名1〕 → 〔人名１〕）。"""
    out = []
    for c in text:
        if "a" <= c <= "z" or "ａ" <= c <= "ｚ":
            c = chr(ord(c) - 32)
        if "A" <= c <= "Z" or "0" <= c <= "9":
            c = chr(ord(c) + 0xFEE0)
        out.append(c)
    return "".join(out)


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


def make_token(kind, label):
    """記号を作る。label は記号の字（番号なら英字にする）。"""
    if isinstance(label, int):
        label = number_to_letters(label)
    return f"{OPEN}{kind}{label}{CLOSE}"


def normalize_token(token):
    """記号の英字・数字を全角にそろえる（英字は大文字）。"""
    return to_wide(token)


def token_label(token):
    """記号の字（〔人名ＹＴ〕 → ＹＴ）。記号でなければ None。"""
    m = TOKEN_RE.fullmatch(normalize_token(token))
    return m.group(2) if m else None


def overlaps_token(word):
    """語が記号の一部になりうるか（VA仮名化 basDictionary.OverlapsToken と同じ判定）。

    記号の字を自由にした（2026-10-25）ので、この判定ですべての重なりは防げない。置き換えるときは、文章にある記号の
    中を飛ばす（Dictionary.spans）。この判定は、英字1字などをうっかり登録しないためにも残す。"""
    wide = "".join(chr(ord(c) + 0xFEE0) if "A" <= c <= "Z" else c for c in word)   # 小文字の「Smith」は英字だけとみない
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
        self.used = {k: set() for k in KINDS}   # 種別ごとに、使ったことのある記号の字（解除しても残す）
        self.released = {}      # 解除した・付け替えた記号 → その記号の前の語（メモリの中だけ）

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

    def next_letters(self, kind):
        """その種別で、まだ使っていない、いちばん小さい英字（自動で振る英字。2026-10-25 班長決定。それまでは、
        使った英字のいちばん大きいものの次だった。利用者がＸを選んでも、自動はＡから詰めて振る）。"""
        n = 1
        while number_to_letters(n) in self.used[kind]:
            n += 1
        return number_to_letters(n)

    def check_token(self, kind, letters, keep=None):
        """種別と記号の字（英字・数字・漢字など。字数の制限なし。半角の英数字・小文字は全角の大文字にそろえる。
        2026-10-25 班長指示）から記号を作り、使えるかを確かめて返す。今ほかの語に使っている
        記号は使えない（NotRegistrable）。解除した記号は使える（別の語に付けるときは、画面で reuse_warning を
        確かめる）。keep は、今その記号を持っている Entry（記号を変えずに直すとき）。"""
        if kind not in KINDS:
            raise ValueError(kind)
        label = to_wide(letters.strip(" 　"))
        if not label:
            raise NotRegistrable("記号の字を入れてください（英字・数字・漢字など）。")
        if not _LABEL_RE.fullmatch(label):
            raise NotRegistrable("記号の字には、文字（英字・漢字・かな）と数字だけを使えます（空白・括弧・記号は使えません）。")
        token = make_token(kind, label)
        if keep is not None and keep.token == token:
            return token
        e = self.find(token)
        if e is not None:
            raise NotRegistrable(f"{token} は、「{e.word}」に使っています。")
        return token

    def reuse_warning(self, token, word):
        """記号 token を語 word に付けるとき、その記号を前に別の語に使っていれば、確かめる文を返す（なければ None）。
        前の語が分からない記号（構文ファイルにあって、元の語が求まらなかったもの）も確かめる。"""
        m = TOKEN_RE.fullmatch(normalize_token(token))
        if not m or m.group(2) not in self.used[m.group(1)] or self.find(token) is not None:
            return None          # 使ったことのない記号・今使っている記号（今使っている記号は check_token で断る）
        before = self.released.get(normalize_token(token))
        if before == trim_selection(word):
            return None
        who = f"「{before}」" if before else "別の語"
        return (f"{token} は、この文書で前に{who}に使った記号です。\n"
                f"AI の前の回答にこの記号が残っていると、取り込むときに「{trim_selection(word)}」に戻ります。\n"
                "同じ AI の会話を続けているときは、別の記号を選ぶことをおすすめします。\n\n"
                f"{token} を付けますか？")

    def register(self, word, kind, letters=None):
        """語を登録し、記号を返す。すでに登録されている語なら、その記号を返す。letters（記号の字）を選んでいれば、
        その記号にする（使えなければ NotRegistrable）。"""
        word = trim_selection(word)
        if kind not in KINDS:
            raise ValueError(kind)
        if word in self.entries:
            return self.entries[word].token
        self.check(word)
        token = self.check_token(kind, letters if letters else self.next_letters(kind))
        self.entries[word] = Entry(word, kind, token)
        self._note(token)
        self.released.pop(token, None)
        return token

    def _note(self, token):
        m = TOKEN_RE.fullmatch(normalize_token(token))
        if m:
            self.used[m.group(1)].add(m.group(2))

    def add_known(self, word, token):
        """構文ファイルと PDF の突き合わせで求めた対応を加える（記号はそのまま使う）。"""
        m = TOKEN_RE.fullmatch(normalize_token(token))
        if not m:
            raise ValueError(token)
        self.entries[word] = Entry(word, m.group(1), normalize_token(token))
        self._note(token)

    def note_used(self, token):
        """構文ファイルにある記号の英字を、使ったことのあるものとして覚える（元の語が分からない記号も）。"""
        self._note(token)

    def unregister(self, word_or_token):
        """登録を解除する（語でも記号でもよい）。解除した記号と前の語は覚えておく（別の語に付けるときに確かめる）。"""
        key = normalize_token(trim_selection(word_or_token))
        for word, e in list(self.entries.items()):
            if word == key or e.token == key:
                del self.entries[word]
                self.released[e.token] = e.word
                return e
        return None

    def rename(self, word_or_token, new_word):
        """登録した語の元の語を変え、前の語を返す（記号は変えない。登録した語の誤りを、記号を変えずに直す。
        解除して登録し直すと英字が変わり、AI の会話の中で同じ人が別の記号になるため。2026-10-25 班長決定）。"""
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

    def change_token(self, word_or_token, kind, letters):
        """登録した語の記号を変え、前の記号を返す（2026-10-25 班長決定。前の記号と語は、解除したものと同じく
        覚えておく）。"""
        e = self.find(word_or_token)
        if e is None:
            raise KeyError(word_or_token)
        token = self.check_token(kind, letters, keep=e)
        old = e.token
        e.kind, e.token = kind, token
        self._note(token)
        if old != token:
            self.released[old] = e.word
            self.released.pop(token, None)
        return old

    def find(self, word_or_token):
        key = normalize_token(trim_selection(word_or_token))
        for e in self.entries.values():
            if e.word == key or e.token == key:
                return e
        return None

    # ---------- 置き換え ----------

    def pseudonymize(self, text):
        """登録した語を記号に置き換える（長い語から先に置き換える。文章にある記号の中は置き換えない）。"""
        out, pos = [], 0
        for a, b, e in self.spans(text):
            out += [text[pos:a], e.token]
            pos = b
        return "".join(out) + text[pos:]

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
        """文章の中の登録した語の位置 [(始め, 終わり, Entry)] を返す（入力欄で色を付ける・記号に置き換えるため。長い語を
        優先し、重ならない）。文章にある記号（〔人名山田〕など）の中は飛ばす（記号の字を自由にしたので、登録した語
        「山田」が記号の中にあることがある。2026-10-25）。"""
        taken = [False] * len(text)
        for m in TOKEN_RE.finditer(text):
            for i in range(m.start(), m.end()):
                taken[i] = True
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
    """文章の中の記号を、出てくる順に（英字・数字を全角にそろえて）返す。"""
    return [normalize_token(m.group(0)) for m in TOKEN_RE.finditer(text)]
