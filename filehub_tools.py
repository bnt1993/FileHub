"""Offline file operations for FileHub VN (stdlib only)."""
import csv
import hashlib
import os
import uuid
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

HEADERS = ("Tên", "Loại", "Kích thước (byte)", "Sửa đổi", "Đường dẫn")

def rename_plan(paths, prefix="", suffix="", start=0):
    plans, seen = [], set()
    sources = {os.path.normcase(os.path.abspath(p)) for p in paths}
    for i, source in enumerate(paths):
        p = Path(source)
        if not p.exists() or p.is_symlink():
            raise ValueError(f"Không tìm thấy file: {p}")
        ext = p.suffix if p.is_file() else ""
        name = f"{prefix}{str(start+i)+'_' if start else ''}{p.stem if p.is_file() else p.name}{suffix}{ext}"
        if not name or name in (".", "..") or any(c in name for c in '<>:"/\\|?*') or name.endswith((" ", ".")):
            raise ValueError(f"Tên không hợp lệ: {name}")
        dest = str(p.with_name(name))
        key = os.path.normcase(os.path.abspath(dest))
        if key in seen or (os.path.lexists(dest) and key not in sources):
            raise FileExistsError(f"Trùng tên: {dest}")
        seen.add(key)
        if key != os.path.normcase(os.path.abspath(source)):
            plans.append((source, dest))
    return plans

def apply_renames(plans):
    staged, done = [], []
    try:
        for src, dest in plans:
            temp = str(Path(src).with_name(".filehub-" + uuid.uuid4().hex + ".tmp"))
            os.rename(src, temp)
            staged.append((src, temp, dest))
        for src, temp, dest in staged:
            os.rename(temp, dest)
            done.append((src, temp, dest))
    except Exception:
        for src, temp, dest in reversed(done):
            if os.path.lexists(dest):
                os.rename(dest, src)
        for src, temp, dest in reversed(staged):
            if os.path.lexists(temp):
                os.rename(temp, src)
        raise

def duplicates(folder, stop=None, limit=50000):
    by_size, count, capped = {}, 0, False
    for root, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            if stop is not None and stop.is_set():
                return [], count, capped
            path = os.path.join(root, name)
            try:
                if os.path.islink(path):
                    continue
                by_size.setdefault(os.path.getsize(path), []).append(path)
                count += 1
                if count >= limit:
                    capped = True
                    break
            except OSError:
                pass
        if capped:
            break
    groups = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        by_hash = {}
        for path in paths:
            if stop is not None and stop.is_set():
                return [], count, capped
            try:
                digest = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024*1024), b""):
                        if stop is not None and stop.is_set():
                            return [], count, capped
                        digest.update(chunk)
                by_hash.setdefault(digest.hexdigest(), []).append(path)
            except OSError:
                pass
        groups.extend(v for v in by_hash.values() if len(v) > 1)
    return groups, count, capped

def export_csv(path, records):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(records)

def export_xlsx(path, records):
    def row_xml(values, n):
        cells = []
        for i, value in enumerate(values):
            ref = f"{chr(65+i)}{n}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        return f'<row r="{n}">' + ''.join(cells) + '</row>'
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="FileHub" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        with z.open("xl/worksheets/sheet1.xml", "w") as sheet:
            sheet.write(b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
            sheet.write(row_xml(HEADERS, 1).encode())
            for n, record in enumerate(records, 2):
                sheet.write(row_xml(record, n).encode())
            sheet.write(b'</sheetData></worksheet>')
