from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

try:
    from docx import Document
    from docx.shared import Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.shared import Pt
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime package
    Document = None
    Cm = None
    WD_ALIGN_PARAGRAPH = None
    WD_TABLE_ALIGNMENT = None
    WD_CELL_VERTICAL_ALIGNMENT = None
    OxmlElement = None
    qn = None
    Pt = None
    DOCX_IMPORT_ERROR = exc
else:
    DOCX_IMPORT_ERROR = None

from app.models.case_referrals import CaseReferral
from app.models.complaint import Complaint
from app.models.department import Department
from app.models.user import User
from app.schemas.case_referral_schema import CaseReferralCreate, CaseReferralOut, DepartmentPublic


def _generate_reference_number() -> str:
    now = datetime.now(timezone.utc)
    return f"CR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{now.microsecond:06d}"


async def get_active_departments(db: AsyncSession):
    result = await db.execute(select(Department).where(Department.is_active.is_(True)).order_by(Department.name.asc()))
    departments = result.scalars().all()
    return [DepartmentPublic.model_validate(dept, from_attributes=True) for dept in departments]


async def get_department_by_id(department_id: int, db: AsyncSession):
    result = await db.execute(select(Department).where(Department.id == department_id))
    department = result.scalars().first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    return DepartmentPublic.model_validate(department, from_attributes=True)


async def get_case_referrals_for_complaint(complaint_id: int, db: AsyncSession):
    result = await db.execute(
        select(CaseReferral)
        .options(selectinload(CaseReferral.department))
        .where(CaseReferral.complaint_id == complaint_id)
        .order_by(CaseReferral.created_at.desc())
    )
    referrals = result.scalars().all()
    return [CaseReferralOut.model_validate(referral, from_attributes=True) for referral in referrals]


async def get_case_referral_by_id(referral_id: int, db: AsyncSession):
    result = await db.execute(
        select(CaseReferral)
        .options(selectinload(CaseReferral.department), selectinload(CaseReferral.complaint))
        .where(CaseReferral.id == referral_id)
    )
    referral = result.scalars().first()
    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")
    return CaseReferralOut.model_validate(referral, from_attributes=True)


async def create_case_referral(payload: CaseReferralCreate, db: AsyncSession):
    result = await db.execute(select(Complaint).where(Complaint.id == payload.complaint_id))
    complaint = result.scalars().first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    result = await db.execute(select(Department).where(Department.id == payload.department_id))
    department = result.scalars().first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    if not department.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected department is inactive")

    referral = CaseReferral(
        complaint_id=payload.complaint_id,
        department_id=payload.department_id,
        designated_officer=payload.designated_officer,
        designated_officer_position=payload.designated_officer_position,
        reason_for_referral=payload.reason_for_referral,
        requested_action=payload.requested_action,
        reference_number=payload.reference_number or _generate_reference_number(),
        receiving_officer=payload.receiving_officer,
        receiving_officer_position=payload.receiving_officer_position,
        letter_date=payload.letter_date or datetime.now(timezone.utc),
    )

    db.add(referral)
    await db.commit()
    await db.refresh(referral)
    return CaseReferralOut.model_validate(referral, from_attributes=True)


async def update_case_referral(referral_id: int, payload: dict[str, Any], db: AsyncSession):
    result = await db.execute(select(CaseReferral).where(CaseReferral.id == referral_id))
    referral = result.scalars().first()
    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")

    if payload.get("department_id"):
        dept_result = await db.execute(select(Department).where(Department.id == payload["department_id"]))
        department = dept_result.scalars().first()
        if not department:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        if not department.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected department is inactive")
        referral.department_id = department.id

    for field in [
        "designated_officer",
        "designated_officer_position",
        "reason_for_referral",
        "requested_action",
        "reference_number",
        "receiving_officer",
        "receiving_officer_position",
        "letter_date",
    ]:
        if field in payload and payload[field] is not None:
            setattr(referral, field, payload[field])

    await db.commit()
    await db.refresh(referral)
    return CaseReferralOut.model_validate(referral, from_attributes=True)


async def build_referral_letter_document(referral: CaseReferral, complaint: Complaint, referring_user: User, db: AsyncSession):
    if DOCX_IMPORT_ERROR is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document generation dependency is not installed. Please install python-docx.",
        )

    if not referral.department:
        result = await db.execute(select(Department).where(Department.id == referral.department_id))
        referral.department = result.scalars().first()

    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(3.6)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.header_distance = Cm(0.45)

    normal_style = document.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(11)
    normal_style.paragraph_format.space_after = Pt(5)
    normal_style.paragraph_format.line_spacing = 1.05

    def add_paragraph(text: str = "", *, bold: bool = False, alignment=None, space_before: int = 0, space_after: int = 5):
        paragraph = document.add_paragraph()
        paragraph.alignment = (
            alignment if alignment is not None else WD_ALIGN_PARAGRAPH.JUSTIFY
        )
        paragraph.paragraph_format.space_before = Pt(space_before)
        paragraph.paragraph_format.space_after = Pt(space_after)
        run = paragraph.add_run(text)
        run.bold = bold
        run.font.name = "Times New Roman"
        run.font.size = Pt(11)
        return paragraph

    def add_labeled_paragraph(label: str, value: str, *, space_after: int = 2):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.paragraph_format.space_after = Pt(space_after)
        label_run = paragraph.add_run(f"{label}: ")
        label_run.bold = True
        label_run.font.name = "Times New Roman"
        label_run.font.size = Pt(11)
        value_run = paragraph.add_run(value)
        value_run.font.name = "Times New Roman"
        value_run.font.size = Pt(11)
        return paragraph

    def display_name(user: User | None) -> str | None:
        if not user:
            return None
        name_parts = [
            user.first_name,
            user.middle_name,
            user.last_name,
            user.suffix,
        ]
        name = " ".join(part.strip() for part in name_parts if part and part.strip())
        return name or None

    def format_tagalog_date(value: datetime) -> str:
        months = (
            "Enero",
            "Pebrero",
            "Marso",
            "Abril",
            "Mayo",
            "Hunyo",
            "Hulyo",
            "Agosto",
            "Setyembre",
            "Oktubre",
            "Nobyembre",
            "Disyembre",
        )
        return f"{value.day} ng {months[value.month - 1]}, {value.year}"

    header = section.header
    header_paragraph = header.paragraphs[0]
    header_paragraph.paragraph_format.space_after = Pt(0)
    header_paragraph.paragraph_format.line_spacing = Pt(1)

    letterhead_width = section.page_width - section.left_margin - section.right_margin
    logo_column_width = Cm(2.5)
    letterhead = header.add_table(rows=1, cols=3, width=letterhead_width)
    letterhead.autofit = False
    letterhead.alignment = WD_TABLE_ALIGNMENT.CENTER
    column_widths = (
        logo_column_width,
        letterhead_width - 2 * logo_column_width,
        logo_column_width,
    )
    for cell, width in zip(letterhead.rows[0].cells, column_widths):
        cell.width = width
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    logo_paths = (
        Path(__file__).resolve().parents[1] / "images" / "stamaria_logo.jpg",
        Path(__file__).resolve().parents[1] / "images" / "sanggunian_logo.png",
    )
    for logo_path in logo_paths:
        if not logo_path.is_file():
            raise FileNotFoundError(f"Referral letter logo not found: {logo_path}")

    for cell, logo_path, alignment in zip(
        (letterhead.cell(0, 0), letterhead.cell(0, 2)),
        logo_paths,
        (WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT),
    ):
        paragraph = cell.paragraphs[0]
        paragraph.alignment = alignment
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.add_run().add_picture(str(logo_path), width=Cm(2.2))

    letterhead_text = letterhead.cell(0, 1)
    header_lines = (
        ("Republika ng Pilipinas", "Times New Roman", 11, True),
        ("Lalawigan ng Laguna", "Times New Roman", 11, True),
        ("BAYAN NG SANTA MARIA", "Times New Roman", 16, True),
        ("Tanggapan ng Sangguniang Bayan", "Old English Text MT", 20, False),
    )
    for index, (text, font_name, font_size, bold) in enumerate(header_lines):
        paragraph = letterhead_text.paragraphs[0] if index == 0 else letterhead_text.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1
        run = paragraph.add_run(text)
        run.bold = bold
        run.font.name = font_name
        run.font.size = Pt(font_size)
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), font_name)
        run._element.get_or_add_rPr().rFonts.set(qn("w:cs"), font_name)

    for cell in letterhead.rows[0].cells:
        cell_properties = cell._tc.get_or_add_tcPr()
        borders = cell_properties.first_child_found_in("w:tcBorders")
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            cell_properties.append(borders)
        bottom_border = OxmlElement("w:bottom")
        bottom_border.set(qn("w:val"), "double")
        bottom_border.set(qn("w:sz"), "12")
        bottom_border.set(qn("w:space"), "3")
        bottom_border.set(qn("w:color"), "000000")
        borders.append(bottom_border)

    barangay_name = complaint.barangay.barangay_name if complaint.barangay else None
    if not barangay_name and referring_user and referring_user.barangay:
        barangay_name = referring_user.barangay

    role = getattr(referring_user, "role", None) if referring_user else None
    is_barangay_official = getattr(role, "value", role) == "barangay_official"
    referring_office = (
        f"Barangay {barangay_name}, Bayan ng Santa Maria, Laguna"
        if is_barangay_official and barangay_name
        else "Pamahalaang Bayan ng Santa Maria, Laguna"
    )
    signer_title = (
        "Opisyal ng Barangay"
        if is_barangay_official
        else "Opisyal ng Pamahalaang Bayan"
    )

    category_name = (
        complaint.category.category_name
        if complaint.category and complaint.category.category_name
        else "Walang nakatalang kategorya"
    )
    complainant_identifier = f"Kaso na may kumpidensyal na ID C-{complaint.id}"
    location = complaint.location_details or barangay_name or "Hindi nakasaad"
    incident_date = (
        format_tagalog_date(complaint.created_at)
        if complaint.created_at
        else "Hindi nakasaad"
    )
    letter_date = (
        format_tagalog_date(referral.letter_date)
        if referral.letter_date
        else format_tagalog_date(datetime.now(timezone.utc))
    )

    add_paragraph(
        "LIHAM NG PAGSASANGGUNI / PAGLILIPAT NG KASO",
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=20,
        space_after=14,
    )

    add_labeled_paragraph("Blg. ng Sanggunian", referral.reference_number or f"CR-{complaint.id}")
    add_labeled_paragraph("Petsa", letter_date)
    add_labeled_paragraph("PARA SA", referral.department.name if referral.department else "Tumatanggap na Kagawaran")
    if referral.department and referral.department.office_address:
        add_labeled_paragraph("Address ng Opisina", referral.department.office_address)
    add_labeled_paragraph(
        "PARA KAY",
        referral.designated_officer or "Tumatanggap na Opisyal / Pinuno ng Tanggapan",
    )
    if referral.designated_officer_position:
        add_labeled_paragraph("KATUNGKULAN", referral.designated_officer_position)
    add_labeled_paragraph("MULA SA", referring_office)
    add_labeled_paragraph(
        "PAKSA",
        f"Pagsasangguni ng Reklamo Blg. {complaint.id} — {category_name}",
        space_after=14,
    )

    salutation = referral.designated_officer or "G./Gng."
    add_paragraph(f"Mahal na {salutation}:", space_after=9)
    add_paragraph(
        f"Magalang naming isinasangguni sa inyong tanggapan ang reklamong "
        f"may kaugnayan sa {category_name}. Iniulat ito ng nagrereklamong "
        f"tinutukoy sa liham na ito bilang {complainant_identifier}. Naganap "
        f"ang insidente sa {location} noong o bandang {incident_date}.",
        space_after=8,
    )
    add_paragraph(
        "Batay sa kasalukuyang impormasyong at mga rekord na makukuha, "
        "narito ang mga pangyayaring kaugnay ng iniulat na insidente:",
        space_after=8,
    )

    for heading, content in (
        ("Buod ng Insidente / Salaysay ng mga Pangyayari", complaint.description or "Walang ibinigay na salaysay ng mga pangyayari."),
        ("Dahilan ng Pagsasangguni", referral.reason_for_referral or "Hindi tinukoy."),
        ("Iminungkahing Aksyon", referral.requested_action or "Hindi tinukoy."),
    ):
        add_paragraph(heading + ":", bold=True, space_before=2, space_after=2)
        paragraph = add_paragraph(content, space_after=7)
        paragraph.paragraph_format.left_indent = Cm(0.8)

    add_paragraph("Mga Kalakip / Suportang Rekord:", bold=True, space_before=2, space_after=2)
    attachment_links = [
        attachment.file_path
        for attachment in (complaint.attachment or [])
        if attachment.file_path
    ]
    attachment_links.extend(
        image.image_url
        for image in (complaint.images or [])
        if image.image_url
    )
    attachment_summary = (
        "\n".join(attachment_links)
        if attachment_links
        else "Walang kalakip na suportang rekord sa reklamo."
    )
    paragraph = add_paragraph(attachment_summary, space_after=9)
    paragraph.paragraph_format.left_indent = Cm(0.8)

    for text in (
        "Dahil dito, magalang naming hinihiling na suriin ng inyong tanggapan "
        "ang kasong ito at magsagawa ng angkop na hakbang alinsunod sa saklaw "
        "ng inyong tungkulin at sa mga umiiral na batas, tuntunin, at pamamaraan. "
        "Mangyaring kumpirmahin ang pagtanggap sa liham na ito at magbigay ng "
        "nararapat na update, alinsunod sa mga patakaran sa pagiging kumpidensyal "
        "at pangangalaga ng datos.",
        "Ang pagsasangguni na ito ay hindi nangangahulugan ng pagtukoy ng "
        "pananagutan o pagpapatunay na naganap ang mga iniulat na alegasyon.",
        "Maraming salamat sa inyong pakikipagtulungan.",
    ):
        paragraph = add_paragraph(text, space_after=8)
        paragraph.paragraph_format.first_line_indent = Cm(0.8)

    add_paragraph("Lubos na gumagalang,", space_before=5, space_after=16)
    add_paragraph(display_name(referring_user) or signer_title, bold=True, space_after=1)
    if display_name(referring_user):
        add_paragraph(signer_title, space_after=1)
    add_paragraph(referring_office, space_after=1)
    contact_details = []
    if referring_user:
        if referring_user.phone_number:
            contact_details.append(referring_user.phone_number)
        if referring_user.email:
            contact_details.append(referring_user.email)
    if contact_details:
        add_paragraph(" | ".join(contact_details), space_after=14)
    else:
        add_paragraph(space_after=14)

    add_paragraph("PAGKILALA NG TUMATANGGAP NA TANGGAPAN", bold=True, space_before=8, space_after=5)
    add_labeled_paragraph("Ipinadala ni", referral.receiving_officer or "________________________________")
    if referral.receiving_officer_position:
        add_labeled_paragraph("Katungkulan", referral.receiving_officer_position)
    else:
        add_labeled_paragraph("Katungkulan", "________________________________")
    add_labeled_paragraph("Petsa at Oras ng Pagtanggap", "________________________________")
    add_labeled_paragraprah("Blg. ng Sanggunian / Pagsubaybay", "________________________________", space_after=0)

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


async def generate_referral_letter(referral_id: int, current_user: User, db: AsyncSession):
    result = await db.execute(
        select(CaseReferral)
        .options(selectinload(CaseReferral.department))
        .where(CaseReferral.id == referral_id)
    )
    referral = result.scalars().first()
    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")

    if current_user.role not in {"lgu_official", "barangay_official", "superadmin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this referral")

    complaint_result = await db.execute(
        select(Complaint)
        .options(
            selectinload(Complaint.category),
            selectinload(Complaint.barangay),
            selectinload(Complaint.user),
            selectinload(Complaint.attachment),
            selectinload(Complaint.images),
        )
        .where(Complaint.id == referral.complaint_id)
    )
    complaint = complaint_result.scalars().first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    document_buffer = await build_referral_letter_document(referral, complaint, current_user, db)
    file_name = f"case_referral_{referral.reference_number or referral.id}.docx"
    return Response(
        content=document_buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )
