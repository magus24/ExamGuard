import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class ImportReport:
    found_rows: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    questions: list
    report: ImportReport


def import_questions(path):
    return import_questions_with_report(path).questions


def import_questions_with_report(path):
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".txt", ".text"}:
        result = parse_text_file_with_report(source)
    elif suffix == ".xlsx":
        result = parse_xlsx_file_with_report(source)
    else:
        raise ValueError("Поддерживаются только файлы .txt и .xlsx.")
    if not result.questions:
        raise ValueError("В файле не найдены вопросы с четырьмя вариантами ответа.")
    return result


def parse_text_file(path):
    return parse_text_file_with_report(path).questions


def parse_text_file_with_report(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    questions = parse_question_text(fix_mojibake(text))
    report = ImportReport(found_rows=len(questions), imported_count=len(questions), skipped_count=0)
    return ImportResult(questions, report)


def parse_xlsx_file(path):
    return parse_xlsx_file_with_report(path).questions


def parse_xlsx_file_with_report(path):
    rows = read_xlsx_rows(path)
    result = parse_rows_as_questions_with_report(rows)
    if result.questions:
        return result

    text = "\n".join("====".join(cell for cell in row if cell) for row in rows)
    questions = parse_question_text(text)
    report = ImportReport(
        found_rows=len(rows),
        imported_count=len(questions),
        skipped_count=max(0, len(rows) - len(questions)),
    )
    return ImportResult(questions, report)


def read_xlsx_rows(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared_strings = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", SPREADSHEET_NS):
                text = "".join(node.text or "" for node in item.findall(".//a:t", SPREADSHEET_NS))
                shared_strings.append(fix_mojibake(text))

        sheet_names = [name for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml")]
        rows = []
        for sheet_name in sheet_names:
            root = ET.fromstring(archive.read(sheet_name))
            for row in root.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
                cells = []
                for cell in row.findall("a:c", SPREADSHEET_NS):
                    value = read_cell_value(cell, shared_strings)
                    cells.append(fix_mojibake(value.strip()) if isinstance(value, str) else "")
                if any(cells):
                    rows.append(cells)
        return rows


def read_cell_value(cell, shared_strings):
    cell_type = cell.get("t")
    value_node = cell.find("a:v", SPREADSHEET_NS)
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//a:t", SPREADSHEET_NS))
    if value_node is None:
        return ""
    value = value_node.text or ""
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    return value


def parse_rows_as_questions(rows):
    return parse_rows_as_questions_with_report(rows).questions


def parse_rows_as_questions_with_report(rows):
    questions = []
    report = ImportReport(found_rows=len(rows))
    for row_number, row in enumerate(rows, start=1):
        values = [clean_token(cell) for cell in row if clean_token(cell)]
        if looks_like_header(values) or not values:
            report.found_rows -= 1
            continue
        if len(values) < 5:
            report.errors.append(f"Строка {row_number}: мало данных для вопроса.")
            continue
        parsed = parse_tokens(values)
        if parsed:
            questions.append(parsed)
            continue
        preview = " | ".join(values[:6])
        if len(preview) > 120:
            preview = preview[:117] + "..."
        report.errors.append(f"Строка {row_number}: нет текста вопроса, 4 ответов или правильного ответа. {preview}")
    report.imported_count = len(questions)
    report.skipped_count = max(0, report.found_rows - report.imported_count)
    return ImportResult(questions, report)


def parse_question_text(text):
    questions = []
    blocks = re.split(r"(?:^|\n)\s*\+{3,}\s*(?:\n|$)", text)
    for block in blocks:
        tokens = [clean_token(token) for token in re.split(r"={3,}", block) if clean_token(token)]
        parsed = parse_tokens(tokens)
        if parsed:
            questions.append(parsed)
    return questions


def parse_tokens(tokens):
    if len(tokens) < 5:
        return None
    question = clean_token(tokens[0])
    answers = []
    correct_index = None
    mark_next = False

    for token in tokens[1:]:
        token = clean_token(token)
        if not token:
            continue
        if token == "#":
            mark_next = True
            continue
        if token.startswith("#"):
            token = clean_token(token[1:])
            mark_next = True
        if not token or token in {"++++", "===="}:
            continue
        if mark_next and correct_index is None:
            correct_index = len(answers)
            mark_next = False
        answers.append(token)
        if len(answers) == 4:
            break

    if not question or len(answers) != 4:
        return None
    return {
        "text": question,
        "answers": answers,
        "correct_index": correct_index if correct_index is not None else 0,
    }


def looks_like_header(values):
    if not values:
        return False
    joined = " ".join(values[:6]).lower()
    return "вопрос" in joined and ("ответ" in joined or "answer" in joined)


def clean_token(value):
    value = str(value).replace("\ufeff", "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def fix_mojibake(text):
    if not isinstance(text, str) or ("Р" not in text and "С" not in text):
        return text
    try:
        fixed = text.encode("cp1251").decode("utf-8")
    except UnicodeError:
        return text
    return fixed if fixed.count("�") <= text.count("�") else text
