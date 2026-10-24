"""1つの文書の作業（組む・保存・開く・構文ファイル・AI の回答の取り込み）。画面からは独立させる。

・実名の文章は、画面の入力欄にあり、このクラスは受け取るだけで、ファイルにはしない（仕様.md の9.1）。
  手元に残すのは、PDF（実名）と構文ファイル（記号）の2つで、いつも同じ版で保存する。
・辞書・対応表はメモリの中だけに持つ（Dictionary）。開き直したときは、構文ファイルと PDF を突き合わせて作り直す。
・構文ファイルは、AI に渡す前も後も、テキストエディターや画面で自由に直してよい（2026-10-23 班長指示）。
  直した構文ファイルを開くと、変わっていない部分から対応表を作り直し、求まらない記号は利用者に尋ねる。
  指示の部分を書き換えていれば、保存するときもその指示を残す。
・過去の文書・テンプレートを使い回すときは、名前を付けて保存・コピーとして開くで、新しい文書ID の文書にする
  （前の事件の PDF と構文ファイルを上書きしない。2026-10-25 班長指示）。
"""
import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import fitz  # PyMuPDF

from . import vadm
from .cleanup import clean_lines
from .doctypes import DOC_TYPES
from .document import parse
from .layout import Typesetter
from .naiyou import DOC_TYPE as NAIYOU
from .pdfwriter import pdf_bytes, read_id, write_pdf
from .pseudonym import Dictionary, tokens_in
from .recover import Recovery, rebuild_dictionary
from .textmap import LayoutMap


@dataclass
class OpenResult:
    text: str                                   # 入力欄に入れる文章（求まらない記号は記号のまま）
    recovery: Recovery = None                   # 構文ファイルから開いたときの突き合わせの結果
    messages: list = field(default_factory=list)  # 利用者に知らせること

    @property
    def unresolved(self):
        """利用者に元の語を尋ねる記号（求まらない記号と、違う語が対応した記号）。"""
        if self.recovery is None:
            return []
        return list(self.recovery.missing) + [t for t in self.recovery.conflicts if t not in self.recovery.missing]


class Session:
    def __init__(self, cfg):
        self.cfg = cfg
        self.new()

    def new(self):
        self.doc_id = vadm.new_doc_id()
        self.version = 0
        self.settings = vadm.Settings(self.cfg.doc_type, self.cfg.page_number,
                                      self.cfg.line_numbers and self.cfg.doc_type != NAIYOU)
        self.dictionary = Dictionary()
        self.prompt = self.cfg.ai_prompt or None    # 利用者が直した AI への指示（None なら既定の指示。オプションで直す）
        self.pdf_path = None
        self.vadm_file = None          # 開いた構文ファイル（None なら決まったフォルダの <文書ID>.vadm）
        self.saved_text = None
        self.saved_body = None          # 保存した構文ファイルの文書（記号入り）
        self.saved_settings = None
        self._opened_body = None
        self.layout_map = None          # 最後に組んだ結果とエディターの位置の対応
        self._vadm_stamp = None        # 最後に書いた・読んだ構文ファイルの中身の指紋（外での書き換えを見分ける）
        # 仮名化を解除した語・変える前の元の語（メモリの中だけ）。保存するとき、構文ファイルに実名のまま残って
        # いれば知らせる（使い回した前の事件の名前の残り。2026-10-25 班長指示）
        self.released = {}

    def detach(self, text=None):
        """今の文書を、新しい文書（新しい文書ID・版 0・保存先なし）にする。文章・仮名化した語の一覧・設定・
        AI への指示は引き継ぎ、開いた PDF と構文ファイルには、もう書かない（名前を付けて保存・コピーとして開く。
        2026-10-25 班長指示）。text があれば、その文章を変えていない状態とする（開いただけでは尋ねない）。"""
        self.doc_id = vadm.new_doc_id()
        self.version = 0
        self.pdf_path = None
        self.vadm_file = None
        self._opened_body = None
        self._vadm_stamp = None
        self.saved_text = text
        self.saved_body = None if text is None else self.body(text)
        self.saved_settings = None if text is None else replace(self.settings)

    # ---------- 状態 ----------

    @property
    def vadm_path(self):
        if self.vadm_file is not None:
            return self.vadm_file
        return Path(self.cfg.vadm_folder) / vadm.file_name(self.doc_id)

    @property
    def doc_type(self):
        return DOC_TYPES[self.settings.doc_type]

    def is_modified(self, text):
        """保存した後に、文章・設定・構文ファイルの中身を変えたか（文末の改行・行末の空白の違いは、
        変えたことにしない。構文ファイル〔記号〕の表示から戻すと、文末の改行がなくなるため）。

        語を仮名化・解除すると、文章が同じでも構文ファイルの中身（記号）が変わるので、変えたことにする
        （保存し直さないまま［コピー］で前の構文ファイルを写し、仮名化する前の実名を AI に渡さないように）。
        """
        if self.saved_text is None:
            return bool(text.strip())
        return (_normalized(text) != _normalized(self.saved_text) or self.settings != self.saved_settings
                or (self.saved_body is not None and _normalized(self.body(text)) != _normalized(self.saved_body)))

    # ---------- 組む ----------

    def typeset(self, text):
        """組む。組んだ結果とエディターの位置の対応（確認表示との連動に使う）を self.layout_map に残す。"""
        cleaned, origins, _ = clean_lines(text)
        ts = Typesetter(self.doc_type)
        paras = parse(cleaned, self.doc_type)
        lines = ts.layout(paras)
        self.layout_map = LayoutMap(ts, lines, paras, cleaned, origins)
        return ts, lines

    def preview_pdf(self, text, highlight=False):
        """確認表示・印刷の PDF（メモリの中だけ。識別子は入れない）。highlight が真なら、確認表示だけの色を付ける
        （蛍光ペンの黄と、仮名化した語の地の色。2026-10-24 班長指示）。"""
        ts, lines = self.typeset(text)
        if highlight and self.dictionary.entries:
            self._mark_pseudonyms(ts, lines, text)
        return pdf_bytes(ts, lines, page_number=self.settings.page_number, highlight=highlight,
                         line_numbers=self.settings.line_numbers)

    def _mark_pseudonyms(self, ts, lines, text):
        """組んだ字のうち、仮名化した語の字に印を付ける（確認表示で、どこが仮名化されているかを示すため）。"""
        marked = set()
        for n, line in enumerate(text.split("\n")):
            for a, b, _ in self.dictionary.spans(line):
                marked.update((n, c) for c in range(a, b))
        if not marked:
            return
        m = self.layout_map
        for ln in lines:
            for g in ln.glyphs:
                if m.glyph_source(ln, g) in marked:
                    g.pseudonym = True
        for piece in getattr(ts, "tables", []):
            for g in piece.glyphs:
                if m.cell_glyph_source(piece, g) in marked:
                    g.pseudonym = True

    # ---------- 構文ファイル ----------

    def body(self, text):
        """記号に置き換えた文書。"""
        return self.dictionary.pseudonymize(text)

    def vadm_text(self, text, version=None):
        return vadm.build(self.doc_id, self.version if version is None else version, self.settings,
                           self.body(text), self.prompt)

    def rewrite_prompt(self):
        """AI への指示を直したとき、保存してある構文ファイルの指示の部分だけを書き直す（版と文書は変えない。
        PDF と同じ版の文書のまま）。"""
        if self.version and self.saved_text is not None and self.vadm_path.exists():
            vadm.write_file(self.vadm_path, self.vadm_text(self.saved_text, self.version))
            self._vadm_stamp = _stamp(self.vadm_path)

    # ---------- 保存（仕様.md の9.1） ----------

    def save(self, text, pdf_path=None):
        """PDF と構文ファイルを、同じ文書ID・同じ（1つ上げた）版で保存する。"""
        pdf_path = Path(pdf_path or self.pdf_path)
        version = self.version + 1
        ts, lines = self.typeset(text)
        write_pdf(ts, lines, str(pdf_path), self.doc_id, version, self.settings.page_number,
                  line_numbers=self.settings.line_numbers)
        vadm.write_file(self.vadm_path, self.vadm_text(text, version))
        self._vadm_stamp = _stamp(self.vadm_path)
        self.version = version
        self.pdf_path = pdf_path
        self.saved_text = text
        self.saved_body = self.body(text)
        self.saved_settings = replace(self.settings)
        self.cfg.remember_pdf_folder(pdf_path.parent)
        self.cfg.doc_type, self.cfg.page_number = self.settings.doc_type, self.settings.page_number
        self.cfg.line_numbers = self.settings.line_numbers

    def save_as(self, text, pdf_path):
        """新しい文書ID の文書として、版 1 の PDF と構文ファイルを保存する（前の PDF と構文ファイルはそのまま）。
        保存できなければ、前の文書に戻す。"""
        keep = {k: getattr(self, k) for k in ("doc_id", "version", "pdf_path", "vadm_file", "_opened_body",
                                              "_vadm_stamp", "saved_text", "saved_body", "saved_settings")}
        self.detach()
        try:
            self.save(text, pdf_path)
        except BaseException:
            for k, v in keep.items():
                setattr(self, k, v)
            raise

    # ---------- 仮名化の解除・元の語の変更 ----------

    def unregister(self, word_or_token):
        """仮名化を解除する（解除した語は、保存するときの確かめのために覚えておく）。"""
        e = self.dictionary.unregister(word_or_token)
        if e:
            self.released[e.word] = None
        return e

    def unregister_all(self):
        """仮名化した語をすべて解除し、解除した Entry のリストを返す。"""
        return [self.unregister(e.token) for e in list(self.dictionary.entries.values())]

    def rename(self, word_or_token, new_word):
        """仮名化した語の元の語を変え、前の語を返す（前の語は、保存するときの確かめのために覚えておく）。"""
        e = self.dictionary.find(word_or_token)
        old = self.dictionary.rename(word_or_token, new_word)
        if e.word != old:
            self.released[old] = None
            self.released.pop(e.word, None)      # 前に解除した語を、改めて元の語にした
        return old

    def released_in(self, text):
        """仮名化を解除した語・変える前の元の語のうち、構文ファイル（記号に置き換えた文書）に実名のまま残るもの
        {語: 数}。"""
        body = self.body(text)
        return {w: body.count(w) for w in self.released if w in body}

    def accept_released(self, words):
        """利用者が残してよいと答えた語を、もう知らせない。"""
        for w in words:
            self.released.pop(w, None)

    # ---------- 外での書き換え ----------

    def vadm_changed_outside(self):
        """構文ファイルが、最後に書いた・読んだときから、VA DocuMakeの外で書き換えられたか
        （テキストエディターで直した、AI の回答を上書き保存した、など。2026-10-23 班長了承）。"""
        path = self.vadm_path
        if not path.exists():
            return False
        return _stamp(path) != self._vadm_stamp

    def outside_vadm_text(self):
        """外で書き換えられた構文ファイルの中身。"""
        return self.vadm_path.read_bytes().decode("utf-8-sig", errors="replace")

    def outside_stamp(self):
        return _stamp(self.vadm_path) if self.vadm_path.exists() else None

    # ---------- AI の回答の取り込み（仕様.md の8.3） ----------

    def review_answer(self, answer_text, current_text):
        """AI の回答を読み、今の文章と比べる。(Content, Review) を返す（文書ID 違い・区切りの行なしは例外）。"""
        content = vadm.parse_text(answer_text)
        r = vadm.review(content, self.doc_id, self.version, self.body(current_text).splitlines(), self.dictionary)
        return content, r

    def apply_answer(self, content, current_text):
        """回答を取り込んだ実名の文章を返す（取り込む前の文章には、画面のエディターの Ctrl+Z で戻る）。"""
        for tok in tokens_in(content.body_text):
            self.dictionary.note_used(tok)
        return self.dictionary.restore(content.body_text)[0]

    # ---------- 開く（仕様.md の9.2） ----------

    def find_pdf(self, doc_id):
        """これまでに PDF を保存したフォルダから、文書ID の合う PDF を探す（版がいちばん新しいもの）。"""
        best = None
        for folder in self.cfg.pdf_folders:
            try:
                candidates = list(Path(folder).glob("*.pdf"))
            except OSError:
                continue
            for p in candidates:
                try:
                    pid = read_id(str(p))
                except Exception:
                    continue
                if pid and pid[0] == doc_id and (best is None or pid[1] > best[1]):
                    best = (p, pid[1])
        return best[0] if best else None

    def open_vadm(self, path, pdf_path=None):
        """構文ファイルを開く。pdf_path が None なら探し、False なら PDF なしで開く（記号は利用者に尋ねる）。

        PDF が見つからないときは FileNotFoundError を出す（画面で利用者に PDF を選んでもらう）。
        """
        content = vadm.read_file(path)
        if pdf_path is None:
            pdf_path = self.find_pdf(content.doc_id)
            if pdf_path is None:
                raise FileNotFoundError(content.doc_id)
        messages = []
        if pdf_path:
            d, r = rebuild_dictionary(content, str(pdf_path))
            pdf_version = read_id(str(pdf_path))[1]
        else:
            d, r = Dictionary(), Recovery(missing=list(dict.fromkeys(tokens_in(content.body_text))))
            for tok in r.missing:
                d.note_used(tok)
            pdf_version = 0
        if pdf_path and pdf_version != content.version:
            messages.append(f"構文ファイル（版 {content.version}）と書式付きファイル（PDF。版 {pdf_version}）の版が違います。"
                            "変わっていない部分から、記号の元の語を求めました。")
        elif pdf_path and not r.exact:
            messages.append("構文ファイルが、書式付きファイル（PDF）を保存した後に直されています。変わっていない部分から、記号の元の語を求めました。")
        self.new()
        self.doc_id = content.doc_id
        self.version = max(content.version, pdf_version)
        if content.settings is not None:
            self.settings = content.settings
        self.prompt = (None if content.prompt is None or content.prompt.rstrip() == vadm.PROMPT.rstrip()
                       else content.prompt)
        self.dictionary = d
        self.pdf_path = Path(pdf_path) if pdf_path else None
        self.vadm_file = Path(path)
        self._vadm_stamp = _stamp(path)
        self._opened_body = content.body_text
        text = d.restore(content.body_text)[0]
        if pdf_path and r.exact and pdf_version == content.version:
            self.saved_text = text
            self.saved_body = self.body(text)
            self.saved_settings = replace(self.settings)
        return OpenResult(text, r, messages)

    def resolve(self, answers):
        """利用者が答えた記号の元の語（{記号: 語}。空の語は記号のまま）を辞書に入れ、開いた文書の文章を返す。"""
        for tok, word in answers.items():
            word = word.strip()
            if word:
                self.dictionary.add_known(word, tok)
        return self.dictionary.restore(self._opened_body or "")[0]

    def open_pdf(self, path):
        """PDF を開く。VA DocuMakeの PDF で構文ファイルが見つかれば、それを開く。

        構文ファイルが見つからない PDF・ほかのソフトで作った PDF は、文字を取り出して素の文章にする
        （見出し・配置は戻さない）。
        """
        pid = read_id(str(path))
        if pid:
            candidate = Path(self.cfg.vadm_folder) / vadm.file_name(pid[0])
            if candidate.exists():
                return self.open_vadm(candidate, path)
        text = pdf_plain_text(path)
        if not text.strip():
            # 字の層のない PDF（OCR していないスキャンなど）は、今の文書を消さずに知らせる（2026-10-24）
            raise NoTextInPdf("この PDF には、取り出せる字がありません（スキャンした画像だけで、OCR の字が入っていません）。\n"
                              "スキャンのソフトで OCR（ScanSnap なら「検索可能な PDF にする」）をしてから、もう一度開いてください。")
        self.new()
        msg = ("この PDF の構文ファイルが見つかりません。" if pid else "VA DocuMakeで作った PDF ではありません。")
        return OpenResult(text, None, [msg + "文字だけを取り出しました（見出し・配置は戻していません）。"])

    def open_text(self, path):
        """テキスト・マークダウンを開く（素材の取り込み用。新しい文書になる）。"""
        raw = Path(path).read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp932", errors="replace")
        self.new()
        return OpenResult(text.replace("\r\n", "\n"))


class NoTextInPdf(ValueError):
    """PDF に字の層がない（OCR していないスキャンなど）。"""


def _stamp(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalized(text):
    return "\n".join(ln.rstrip() for ln in text.strip("\n").splitlines())


def pdf_plain_text(path):
    """PDF の文字を、塊（段落）ごとに行をつないで取り出す。"""
    paras = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            for b in page.get_text("blocks", sort=True):
                if b[6] != 0:      # 画像の塊
                    continue
                text = "".join(s.strip() for s in b[4].splitlines())
                if text and not text.isdigit():
                    paras.append(text)
    return "\n".join(paras)
