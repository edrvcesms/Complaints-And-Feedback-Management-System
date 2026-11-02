from io import BytesIO
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, case, func, select
from app.models.incident_model import IncidentModel
from app.utils.logger import logger
from app.models.user import User
from app.models.barangay import Barangay
from app.models.category import Category
from app.models.complaint import Complaint
from app.models.post_incident_feedback import PostIncidentFeedback
from app.constants.complaint_status import ComplaintStatus
from app.constants.roles import UserRole
from app.schemas.report_schema import ComplaintReportRequest
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import selectinload
from typing import Optional
from app.utils.caching import set_cache, get_cache


APP_TIMEZONE = ZoneInfo("Asia/Manila")


def _format_report_date(value):
  return f"{value.strftime('%B')} {value.day}, {value.year}"


def _display_category_name(category_name):
  return str(category_name).replace("_", " ").replace("-", " ").title()


def _satisfaction_performance(average_rating):
  if average_rating is None:
    return "No Rating"
  if average_rating <= 1.5:
    return "Poor"
  if average_rating < 3:
    return "Below Average"
  if average_rating < 4:
    return "Average"
  if average_rating <= 4.5:
    return "Good"
  return "Excellent"


def _status_group_expression():
  return case(
    (Complaint.status.in_([
      ComplaintStatus.RESOLVED_BY_BARANGAY.value,
      ComplaintStatus.RESOLVED_BY_LGU.value,
    ]), "resolved"),
    (Complaint.status == ComplaintStatus.FORWARDED_TO_LGU.value, "escalated"),
    (Complaint.status == ComplaintStatus.REJECTED.value, "rejected"),
    (Complaint.status.in_([
      ComplaintStatus.SUBMITTED.value,
      ComplaintStatus.REVIEWED_BY_BARANGAY.value,
      ComplaintStatus.REVIEWED_BY_LGU.value,
    ]), "under_review"),
    else_="under_review",
  )


def _report_styles():
  styles = getSampleStyleSheet()
  return {
    "body": ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10, spaceAfter=2),
    "small": ParagraphStyle("ReportSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7, leading=8),
    "header": ParagraphStyle("ReportHeader", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=TA_CENTER),
    "title": ParagraphStyle("ReportTitle", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=4),
    "section": ParagraphStyle("ReportSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=12, spaceBefore=8, spaceAfter=5),
    "table": ParagraphStyle("ReportTable", parent=styles["BodyText"], fontName="Helvetica", fontSize=7, leading=8, alignment=TA_CENTER),
    "table_center": ParagraphStyle("ReportTableCenter", parent=styles["BodyText"], fontName="Helvetica", fontSize=7, leading=8, alignment=TA_CENTER),
  }


def _p(value, style):
  return Paragraph(str(value), style)


def _draw_page(canvas, document):
  canvas.saveState()
  canvas.setFont("Helvetica", 7)
  canvas.drawString(18 * mm, 10 * mm, "Complaints and Feedback Management System")
  canvas.drawRightString(document.pagesize[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
  canvas.restoreState()


def _build_complaint_report_pdf(report: dict) -> bytes:
  styles = _report_styles()
  output = BytesIO()
  document = BaseDocTemplate(
    output,
    pagesize=landscape(A4),
    leftMargin=14 * mm,
    rightMargin=14 * mm,
    topMargin=14 * mm,
    bottomMargin=16 * mm,
    title="General Ov",
    author="Complaints and Feedback Management System",
  )
  frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height, id="normal")
  document.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=_draw_page)])

  story = [
    _p("REPUBLIC OF THE PHILIPPINES", styles["header"]),
    _p("MUNICIPALITY OF SANTA MARIA", styles["header"]),
    _p("PROVINCE OF LAGUNA", styles["header"]),
    Spacer(1, 5 * mm),
    _p("COMPLAINTS AND FEEDBACK MANAGEMENT SYSEM", styles["header"]),
    _p("OVERALL REPORT", styles["title"]),
    _p(f"Reporting Period: {report['period_label']}", styles["body"]),
    _p(f"Date Generated: {report['generated_label']}", styles["body"]),
    Spacer(1, 4 * mm),
    _p("I. EXECUTIVE SUMMARY", styles["section"]),
  ]

  summary_rows = [[_p("COMPLAINT STATISTICS", styles["table"]), _p("TOTAL", styles["table_center"])]]
  for label, key in [
    ("Total Complaints Received", "total"),
    ("Resolved", "resolved"),
    ("Under Review", "under_review"),
    ("Escalated", "escalated"),
    ("Rejected", "rejected"),
  ]:
    summary_rows.append([_p(label, styles["table"]), _p(report["summary"][key], styles["table_center"])])
  summary = Table(summary_rows, colWidths=[90 * mm, 25 * mm], repeatRows=1)
  summary.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
  ]))
  story.append(summary)
  story.append(Spacer(1, 2 * mm))
  story.append(_p(report["summary_interpretation"], styles["body"]))
  story.append(_p("II. DISTRIBUTION OF COMPLAINTS BY BARANGAY", styles["section"]))

  status_headers = ["No.", "Barangay", "Total", "Resolved", "Under Review", "Escalated", "Rejected"]
  distribution_rows = [[_p(value, styles["table_center"] if index != 1 else styles["table"]) for index, value in enumerate(status_headers)]]
  for index, row in enumerate(report["barangays"], 1):
    distribution_rows.append([_p(index, styles["table_center"]), _p(row["name"], styles["table"])] + [_p(row[key], styles["table_center"]) for key in ["total", "resolved", "under_review", "escalated", "rejected"]])
  distribution_rows.append([_p("", styles["table_center"]), _p("TOTAL", styles["table"])] + [_p(report["summary"][key], styles["table_center"]) for key in ["total", "resolved", "under_review", "escalated", "rejected"]])
  distribution = Table(distribution_rows, colWidths=[8 * mm, 38 * mm, 15 * mm, 18 * mm, 20 * mm, 17 * mm, 17 * mm], repeatRows=1)
  distribution.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.35, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EDEDED")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
  ]))
  story.append(distribution)
  story.append(Spacer(1, 2 * mm))
  story.append(_p(report["barangay_interpretation"], styles["body"]))
  story.append(_p("III. CLASSIFICATION OF COMPLAINTS BY BARANGAY", styles["section"]))

  category_headers = ["No.", "Barangay", *[_display_category_name(category) for category in report["categories"]], "Total"]
  category_rows = [[_p(value, styles["table_center"] if index != 1 else styles["table"]) for index, value in enumerate(category_headers)]]
  for index, row in enumerate(report["barangays"], 1):
    category_rows.append([_p(index, styles["table_center"]), _p(row["name"], styles["table"])] + [_p(row["categories"][category], styles["table_center"]) for category in report["categories"]] + [_p(row["total"], styles["table_center"])])
  category_rows.append([_p("", styles["table_center"]), _p("TOTAL", styles["table"])] + [_p(report["category_totals"][category], styles["table_center"]) for category in report["categories"]] + [_p(report["summary"]["total"], styles["table_center"])])
  # Keep numeric category columns compact; long category names wrap in the header
  # instead of stretching every column across the full page.
  category_column_width = 15 * mm
  category = Table(
    category_rows,
    colWidths=[
      8 * mm,
      40 * mm,
      *([category_column_width] * len(report["categories"])),
      15 * mm,
    ],
    repeatRows=1,
  )
  category.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.35, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EDEDED")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
  ]))
  story.append(category)
  story.append(Spacer(1, 4 * mm))
  story.append(_p("IV. CATEGORY INTERPRETATION", styles["section"]))
  story.append(_p(report["category_interpretation"], styles["body"]))
  document.build(story)
  return output.getvalue()


def _build_barangay_complaint_report_pdf(report: dict) -> bytes:
  styles = _report_styles()
  output = BytesIO()
  document = BaseDocTemplate(
    output,
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=18 * mm,
    topMargin=16 * mm,
    bottomMargin=18 * mm,
    title="Barangay Complaint Report",
    author="Complaints and Feedback Management System",
  )
  frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height, id="normal")
  document.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=_draw_page)])

  story = [
    ## the font must be Times New Roman 
    _p("REPUBLIC OF THE PHILIPPINES", styles["header"]),
    _p("MUNICIPALITY OF SANTA MARIA", styles["header"]),
    _p("BARANGAY COMPLAINT REPORT", styles["title"]),
    _p(f"Barangay: {report['barangay_name']}", styles["body"]),
    _p(f"Reporting Period: {report['period_label']}", styles["body"]),
    _p(f"Date Generated: {report['generated_label']}", styles["body"]),
    Spacer(1, 4 * mm),
    _p("I. WRITTEN INTERPRETATION", styles["section"]),
    _p(report["interpretation"], styles["body"]),
    Spacer(1, 2 * mm),
    _p("II. COMPLAINT STATUS SUMMARY", styles["section"]),
  ]

  summary_rows = [[_p("STATUS", styles["table"]), _p("TOTAL", styles["table_center"])]]
  for label, key in [
    ("Total Complaints Submitted During Period", "total"),
    ("Resolved", "resolved"),
    ("Forwarded to LGU", "forwarded"),
    ("Still Under Review", "under_review"),
  ]:
    summary_rows.append([_p(label, styles["table"]), _p(report["summary"][key], styles["table_center"])])
  summary = Table(summary_rows, colWidths=[105 * mm, 25 * mm], repeatRows=1)
  summary.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
  ]))
  story.append(summary)
  story.append(Spacer(1, 4 * mm))
  story.append(_p("III. STATUS INTERPRETATION", styles["section"]))
  interpretation_rows = [
    [_p("Metric", styles["table"]), _p("Interpretation", styles["table"])],
    [_p("Resolved", styles["table"]), _p("Complaints completed by the barangay or LGU during the selected period.", styles["table"])],
    [_p("Forwarded to LGU", styles["table"]), _p("Complaints escalated to the LGU for further action.", styles["table"])],
    [_p("Still Under Review", styles["table"]), _p("Complaints that remain submitted or are being reviewed.", styles["table"])],
  ]
  interpretations = Table(interpretation_rows, colWidths=[38 * mm, 92 * mm], repeatRows=1)
  interpretations.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1E8")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
  ]))
  story.append(interpretations)
  story.append(Spacer(1, 4 * mm))
  story.append(_p("IV. COMPLAINT CATEGORIES", styles["section"]))
  category_rows = [[_p("CATEGORY", styles["table"]), _p("TOTAL COMPLAINTS", styles["table_center"])]]
  for category in report["categories"]:
    category_rows.append([
      _p(_display_category_name(category["name"]), styles["table"]),
      _p(category["total"], styles["table_center"]),
    ])
  if not report["categories"]:
    category_rows.append([_p("No complaints recorded during this period.", styles["table"]), _p(0, styles["table_center"])])
  categories = Table(category_rows, colWidths=[105 * mm, 25 * mm], repeatRows=1)
  categories.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
  ]))
  story.append(categories)
  story.append(Spacer(1, 3 * mm))
  story.append(_p(report["category_interpretation"], styles["body"]))
  story.append(Spacer(1, 4 * mm))
  story.append(_p("V. RESIDENT SATISFACTION BY CATEGORY", styles["section"]))
  satisfaction_rows = [[
    _p("CATEGORY", styles["table"]),
    _p("RESPONSES", styles["table_center"]),
    _p("AVERAGE RATING", styles["table_center"]),
    _p("PERFORMANCE", styles["table_center"]),
  ]]
  for category in report["satisfaction_by_category"]:
    satisfaction_rows.append([
      _p(_display_category_name(category["name"]), styles["table"]),
      _p(category["responses"], styles["table_center"]),
      _p(category["average_rating"], styles["table_center"]),
      _p(category["performance"], styles["table_center"]),
    ])
  if not report["satisfaction_by_category"]:
    satisfaction_rows.append([
      _p("No resident satisfaction ratings recorded during this period.", styles["table"]),
      _p(0, styles["table_center"]),
      _p("N/A", styles["table_center"]),
      _p("No Rating", styles["table_center"]),
    ])
  satisfaction = Table(satisfaction_rows, colWidths=[62 * mm, 22 * mm, 28 * mm, 28 * mm], repeatRows=1)
  satisfaction.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
  ]))
  story.append(satisfaction)
  story.append(Spacer(1, 3 * mm))
  story.append(_p(report["satisfaction_interpretation"], styles["body"]))
  document.build(story)
  return output.getvalue()


async def generate_barangay_complaint_report(request: ComplaintReportRequest, current_user: User, db: AsyncSession) -> bytes:
  if current_user.role != UserRole.BARANGAY_OFFICIAL or not current_user.barangay_account:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
  if request.from_date > request.to_date:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from_date must not be after to_date")

  try:
    start_local = datetime.combine(request.from_date, time.min, tzinfo=APP_TIMEZONE)
    end_local = datetime.combine(request.to_date + timedelta(days=1), time.min, tzinfo=APP_TIMEZONE)
    date_filter = (
      Complaint.barangay_id == current_user.barangay_account.barangay_id,
      Complaint.created_at >= start_local.astimezone(timezone.utc),
      Complaint.created_at < end_local.astimezone(timezone.utc),
    )
    status_group = case(
      (Complaint.status.in_([ComplaintStatus.RESOLVED_BY_BARANGAY.value, ComplaintStatus.RESOLVED_BY_LGU.value]), "resolved"),
      (Complaint.status == ComplaintStatus.FORWARDED_TO_LGU.value, "forwarded"),
      (Complaint.status.in_([ComplaintStatus.SUBMITTED.value, ComplaintStatus.REVIEWED_BY_BARANGAY.value, ComplaintStatus.REVIEWED_BY_LGU.value]), "under_review"),
      else_="other",
    ).label("status_group")
    rows = (await db.execute(
      select(status_group, func.count(Complaint.id))
      .where(*date_filter)
      .group_by(status_group)
    )).all()
    counts = {group: count for group, count in rows}
    summary = {
      "total": sum(counts.values()),
      "resolved": counts.get("resolved", 0),
      "forwarded": counts.get("forwarded", 0),
      "under_review": counts.get("under_review", 0),
    }
    category_rows = (await db.execute(
      select(Category.category_name, func.count(Complaint.id))
      .join(Category, Category.id == Complaint.category_id)
      .where(*date_filter)
      .group_by(Category.category_name)
      .order_by(func.count(Complaint.id).desc(), Category.category_name.asc())
    )).all()
    category_totals = [{"name": name, "total": count} for name, count in category_rows]
    if category_totals:
      top_category = category_totals[0]
      category_interpretation = (
        f"The most complained category was {_display_category_name(top_category['name'])} "
        f"with {top_category['total']} complaint(s)."
      )
    else:
      category_interpretation = "No complaint categories were recorded during this period."
    satisfaction_rows = (await db.execute(
      select(
        Category.category_name,
        func.count(PostIncidentFeedback.id),
        func.avg(PostIncidentFeedback.ratings),
      )
      .join(Complaint, Complaint.category_id == Category.id)
      .join(PostIncidentFeedback, PostIncidentFeedback.complaint_id == Complaint.id)
      .where(*date_filter)
      .group_by(Category.category_name)
      .order_by(func.avg(PostIncidentFeedback.ratings).asc(), Category.category_name.asc())
    )).all()
    satisfaction_by_category = [
      {
        "name": name,
        "responses": responses,
        "average_rating": round(float(average_rating), 2),
        "performance": _satisfaction_performance(float(average_rating)),
      }
      for name, responses, average_rating in satisfaction_rows
    ]
    overall_satisfaction = (await db.execute(
      select(func.avg(PostIncidentFeedback.ratings))
      .join(Complaint, PostIncidentFeedback.complaint_id == Complaint.id)
      .where(*date_filter)
    )).scalar_one()
    if overall_satisfaction is None:
      satisfaction_interpretation = "No resident satisfaction ratings were recorded during this period."
    else:
      overall_rating = round(float(overall_satisfaction), 2)
      satisfaction_interpretation = (
        f"The barangay's overall resident satisfaction rating was {overall_rating:.2f} out of 5.00, "
        f"which is {_satisfaction_performance(overall_rating).lower()}."
      )
    period_label = f"{_format_report_date(request.from_date)} - {_format_report_date(request.to_date)}"
    barangay = (await db.execute(
      select(Barangay).where(Barangay.id == current_user.barangay_account.barangay_id)
    )).scalar_one_or_none()
    if not barangay:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Barangay not found")
    report = {
      "barangay_name": barangay.barangay_name,
      "period_label": period_label,
      "generated_label": _format_report_date(datetime.now(APP_TIMEZONE).date()),
      "summary": summary,
      "categories": category_totals,
      "category_interpretation": category_interpretation,
      "satisfaction_by_category": satisfaction_by_category,
      "satisfaction_interpretation": satisfaction_interpretation,
      "interpretation": (
        f"During {period_label}, {summary['total']} complaint(s) were recorded for "
        f"{barangay.barangay_name}. Of these, "
        f"{summary['resolved']} were resolved, {summary['forwarded']} were forwarded to the LGU, "
        f"and {summary['under_review']} remain under review."
      ),
    }
    return _build_barangay_complaint_report_pdf(report)
  except HTTPException:
    raise
  except Exception as exc:
    logger.exception("Error generating barangay complaint report: %s", exc)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while generating the report.") from exc


async def generate_municipal_complaint_report(request: ComplaintReportRequest, current_user: User, db: AsyncSession) -> bytes:
  if current_user.role not in [UserRole.LGU_OFFICIAL, UserRole.SUPERADMIN]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
  if request.from_date > request.to_date:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from_date must not be after to_date")

  try:
    start_local = datetime.combine(request.from_date, time.min, tzinfo=APP_TIMEZONE)
    end_local = datetime.combine(request.to_date + timedelta(days=1), time.min, tzinfo=APP_TIMEZONE)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    date_filter = (Complaint.created_at >= start_utc, Complaint.created_at < end_utc)

    barangays = (await db.execute(select(Barangay).order_by(Barangay.barangay_name))).scalars().all()
    categories = (await db.execute(select(Category).order_by(Category.id))).scalars().all()
    status_group = _status_group_expression().label("status_group")

    status_rows = (await db.execute(
      select(Complaint.barangay_id, status_group, func.count(Complaint.id))
      .where(*date_filter)
      .group_by(Complaint.barangay_id, status_group)
    )).all()
    category_rows = (await db.execute(
      select(Complaint.barangay_id, Complaint.category_id, func.count(Complaint.id))
      .where(*date_filter)
      .group_by(Complaint.barangay_id, Complaint.category_id)
    )).all()

    barangay_data = {barangay.id: {"name": barangay.barangay_name, "total": 0, "resolved": 0, "under_review": 0, "escalated": 0, "rejected": 0, "categories": {category.category_name: 0 for category in categories}} for barangay in barangays}
    category_name_by_id = {category.id: category.category_name for category in categories}
    for barangay_id, status_group_value, count in status_rows:
      if barangay_id in barangay_data and status_group_value in barangay_data[barangay_id]:
        barangay_data[barangay_id][status_group_value] += count
    for barangay_id, category_id, count in category_rows:
      category_name = category_name_by_id.get(category_id)
      if barangay_id in barangay_data and category_name is not None:
        barangay_data[barangay_id]["categories"][category_name] += count

    report_barangays = list(barangay_data.values())
    for row in report_barangays:
      row["total"] = sum(row[key] for key in ["resolved", "under_review", "escalated", "rejected"])
      row["category_total"] = sum(row["categories"].values())
    summary = {key: sum(row[key] for row in report_barangays) for key in ["total", "resolved", "under_review", "escalated", "rejected"]}
    active_barangays = [row for row in report_barangays if row["total"] > 0]
    if active_barangays:
      top_barangay = max(active_barangays, key=lambda row: (row["total"], row["name"]))
      barangay_interpretation = (
        f"{top_barangay['name']} has the most complaints with {top_barangay['total']} "
        f"complaint(s) during the selected period."
      )
    else:
      barangay_interpretation = "No barangay complaints were recorded during this period."
    summary_interpretation = (
      f"The municipality recorded {summary['total']} complaint(s): {summary['resolved']} resolved, "
      f"{summary['under_review']} under review, {summary['escalated']} escalated, and "
      f"{summary['rejected']} rejected."
    )
    all_category_totals = {category.category_name: sum(row["categories"][category.category_name] for row in report_barangays) for category in categories}
    category_totals = {
      category_name: total
      for category_name, total in all_category_totals.items()
      if total > 0
    }
    if category_totals:
      top_category_name, top_category_total = max(category_totals.items(), key=lambda item: (item[1], item[0]))
      category_interpretation = (
        f"The most complained category across the municipality was "
        f"{_display_category_name(top_category_name)} with {top_category_total} complaint(s). "
        f"The category table includes only categories with at least one complaint during the selected period."
      )
    else:
      category_interpretation = "No complaint categories were recorded during this period."
    report = {
      "summary": summary,
      "summary_interpretation": summary_interpretation,
      "barangays": report_barangays,
      "barangay_interpretation": barangay_interpretation,
      "categories": list(category_totals),
      "category_totals": category_totals,
      "category_interpretation": category_interpretation,
      "period_label": f"{_format_report_date(request.from_date)} - {_format_report_date(request.to_date)}",
      "generated_label": _format_report_date(datetime.now(APP_TIMEZONE).date()),
    }
    return _build_complaint_report_pdf(report)
  except HTTPException:
    raise
  except Exception as exc:
    logger.exception("Error generating municipal complaint report: %s", exc)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while generating the report.") from exc

async def get_monthly_report(barangay_id: int, user_id: int, db: AsyncSession, month: Optional[int] = None, year: Optional[int] = None):
  try:
    now = datetime.now(timezone.utc)
    target_month = month if month is not None else now.month
    target_year = year if year is not None else now.year
    
    cache_key = f"monthly_report_by_barangay:{barangay_id}:{target_month}:{target_year}"
    cached_report = await get_cache(cache_key)
    if cached_report:
      logger.info(f"Monthly report for barangay {barangay_id} ({target_month}/{target_year}) retrieved from cache")
      return cached_report
    
    result = await db.execute(select(User).where(User.id == user_id))
    current_user = result.scalar_one_or_none()
    if not current_user:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if current_user.role not in [UserRole.BARANGAY_OFFICIAL, UserRole.LGU_OFFICIAL]:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

    barangay_result = await db.execute(select(Barangay).where(Barangay.id == barangay_id))
    barangay = barangay_result.scalar_one_or_none()
    if not barangay:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Barangay not found")
    
    if not (1 <= target_month <= 12):
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month. Must be between 1 and 12.")
    if not (2020 <= target_year <= 2100):
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid year.")
    
    start_date = datetime(target_year, target_month, 1)
    
    if target_month == 12:
      end_date = datetime(target_year + 1, 1, 1)
    else:
      end_date = datetime(target_year, target_month + 1, 1)
    
    categories_result = await db.execute(select(Category))
    all_categories = categories_result.scalars().all()
    
    category_summary = {}
    for category in all_categories:
      category_summary[category.category_name] = {
        "incidents": [],
        "total_complaint_count": 0
      }
    
    result = await db.execute(
      select(IncidentModel)
      .options(selectinload(IncidentModel.category))
      .where(
        and_(
          IncidentModel.barangay_id == barangay_id,
          IncidentModel.first_reported_at >= start_date,
          IncidentModel.first_reported_at < end_date
        )
      )
    )
    incidents = result.scalars().all()
    
    for incident in incidents:
      category_name = incident.category.category_name if incident.category else None
      
      if category_name and category_name in category_summary:
        category_summary[category_name]["incidents"].append({
          "incident_id": incident.id,
          "incident_title": incident.title,
          "complaint_count": incident.complaint_count,
          "first_reported_at": incident.first_reported_at.isoformat() if incident.first_reported_at else None,
          "last_reported_at": incident.last_reported_at.isoformat() if incident.last_reported_at else None
        })
        category_summary[category_name]["total_complaint_count"] += incident.complaint_count

    report_data = []
    for category_name, summary in category_summary.items():
      report_data.append({
        "category": category_name,
        "total_incidents": len(summary["incidents"]),
        "incidents": summary["incidents"],
        "total_complaint_count": summary["total_complaint_count"]
      })

    report = {
      "barangay": {
        "id": barangay.id,
        "name": barangay.barangay_name,
        "address": barangay.barangay_address,
        "contact_number": barangay.barangay_contact_number,
        "email": barangay.barangay_email,
      },
      "report_period": {
        "month": target_month,
        "year": target_year,
        "month_name": start_date.strftime("%B"),
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat()
      },
      "data": report_data
    }
    
    await set_cache(cache_key, report, expiration=3600)
    logger.info(f"Monthly report for barangay {barangay_id} ({target_month}/{target_year}) retrieved from database and cached")
    
    return report
  
  except HTTPException:
    raise
  
  except Exception as e:
    logger.exception(f"Error generating monthly report for barangay ID {barangay_id}: {str(e)}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while generating the report.")
  

async def get_overall_reports(db: AsyncSession, month: Optional[int] = None, year: Optional[int] = None):
  try:
    now = datetime.now(timezone.utc)
    target_month = month if month is not None else now.month
    target_year = year if year is not None else now.year
    
    cache_key = f"overall_report:{target_month}:{target_year}"
    cached_report = await get_cache(cache_key)
    if cached_report:
      logger.info(f"Overall report for {target_month}/{target_year} retrieved from cache")
      return cached_report
    
    if not (1 <= target_month <= 12):
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month. Must be between 1 and 12.")
    if not (2020 <= target_year <= 2100):
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid year.")
    
    start_date = datetime(target_year, target_month, 1)
    
    if target_month == 12:
      end_date = datetime(target_year + 1, 1, 1)
    else:
      end_date = datetime(target_year, target_month + 1, 1)
    
    categories_result = await db.execute(select(Category))
    all_categories = categories_result.scalars().all()
    
    category_summary = {}
    for category in all_categories:
      category_summary[category.category_name] = {
        "incidents": [],
        "total_complaint_count": 0
      }
    
    result = await db.execute(
      select(IncidentModel)
      .options(selectinload(IncidentModel.category))
      .where(
        and_(
          IncidentModel.first_reported_at >= start_date,
          IncidentModel.first_reported_at < end_date
        )
      )
    )
    incidents = result.scalars().all()
    for incident in incidents:
      category_name = incident.category.category_name if incident.category else None
      if category_name in category_summary:
        category_summary[category_name]["incidents"].append({
          "incident_id": incident.id,
          "incident_title": incident.title,
          "complaint_count": incident.complaint_count,
        })
        category_summary[category_name]["total_complaint_count"] += incident.complaint_count
    report = [{
      "category": category_name,
      "total_incidents": len(summary["incidents"]),
      "incidents": summary["incidents"],
      "total_complaint_count": summary["total_complaint_count"],
    } for category_name, summary in category_summary.items()]
    await set_cache(cache_key, report, expiration=3600)
    return report
  except HTTPException:
    raise
  except Exception as exc:
    logger.exception("Error generating overall report: %s", exc)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while generating the report.") from exc
    