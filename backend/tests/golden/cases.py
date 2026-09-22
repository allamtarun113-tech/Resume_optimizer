"""Golden resume/JD pairs: extracted profile + requirements + recorded EvidenceMatcher output.

Expected results live next to this file as <name>.json. Regenerate after an intended
scoring change with `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py` and review the diff.
"""

from dataclasses import dataclass

from app.schemas.matching import EvidenceJudgements
from app.schemas.profile import StudentProfile
from app.schemas.requirements import JobRequirements
from tests.builders import cert, edu, job, judged, profile, project, req, reqs, skill


@dataclass(frozen=True)
class GoldenCase:
    name: str
    profile: StudentProfile
    requirements: JobRequirements
    judgements: EvidenceJudgements


SUPP = "supplementary:doc-1"

CASES = [
    GoldenCase(
        name="backend_new_grad",
        profile=profile(
            skills=[
                skill("Python"),
                skill("Java"),
                skill("SQL"),
                skill("FastAPI"),
                skill("Git"),
                skill("Docker"),
                skill("PostgreSQL"),
                skill("FastAPI", "project", within="Campus Food Ordering App"),
                skill("PostgreSQL", "project", within="Campus Food Ordering App"),
                skill("Redis", "project", within="Campus Food Ordering App"),
                skill("Go", "experience", within="Backend Intern"),
                skill("Kubernetes", "project", source=SUPP, within="Campus Food Ordering App"),
                skill("GitHub Actions", "project", source=SUPP, within="Campus Food Ordering App"),
            ],
            projects=[
                project("Campus Food Ordering App", ["FastAPI", "PostgreSQL", "Redis", "JWT"]),
                project("Campus Food Ordering App", ["Docker", "Kubernetes"], source=SUPP),
            ],
            experience=[job("Backend Intern", "Acme Payments", "2025-05", "2025-07", ["Go"])],
            education=[edu("B.Tech", "Computer Science")],
            certifications=[cert("AWS Certified Cloud Practitioner")],
        ),
        requirements=reqs(
            req("Python"),
            req("FastAPI"),
            req("PostgreSQL"),
            req("REST APIs"),
            req("Docker", importance="nice"),
            req("Kubernetes", importance="nice"),
            req("CI/CD", importance="nice"),
            req("AWS", importance="nice"),
            req("Bachelor's in Computer Science", "education"),
            req("Communication", "soft_skill"),
            title="Backend Engineer (New Grad)",
        ),
        judgements=judged(
            ("R4", "direct", ["P1", "K4"]),
            ("R8", "direct", ["C1"]),
            ("R9", "direct", ["E1"]),
            ("R10", "none", []),
        ),
    ),
    GoldenCase(
        name="data_analyst",
        profile=profile(
            skills=[
                skill("Excel"),
                skill("Tableau"),
                skill("Python (pandas)"),
                skill("SQL"),
                skill("Tableau", "project", within="Retail sales dashboard"),
                skill("Statistics", "education"),
            ],
            projects=[project("Retail sales dashboard", ["Tableau", "Excel"])],
            education=[edu("M.Sc", "Statistics")],
        ),
        requirements=reqs(
            req("SQL"),
            req("Excel"),
            req("Tableau"),
            req("Power BI", importance="nice"),
            req("Statistics", "domain"),
            req("Data storytelling", "soft_skill"),
            req("Degree in a quantitative field", "education"),
            title="Data Analyst",
        ),
        judgements=judged(
            ("R4", "none", []),
            ("R6", "implied", ["P1"]),
            ("R7", "direct", ["E1"]),
        ),
    ),
    GoldenCase(
        name="ml_engineer_with_years",
        profile=profile(
            skills=[
                skill("PyTorch"),
                skill("PyTorch", "experience", within="ML Intern"),
                skill("scikit-learn"),
                skill("Docker", "project", within="Churn model API"),
                skill("MLflow", "project", source=SUPP, within="Churn model API"),
            ],
            projects=[project("Churn model API", ["scikit-learn", "FastAPI", "Docker"])],
            experience=[
                job("ML Intern", "VisionAI", "2024-06", "2024-12", ["PyTorch"]),
                job(
                    "Research Assistant",
                    "University Lab",
                    "2025-01",
                    "present",
                    ["PyTorch"],
                    kind="research",
                ),
            ],
            education=[edu("B.Tech", "Electronics")],
        ),
        requirements=reqs(
            req("2+ years machine learning experience", "experience", min_years=2),
            req("PyTorch"),
            req("Machine Learning"),
            req("MLOps", importance="nice"),
            req("Master's degree in CS or related", "education", importance="nice"),
            title="Machine Learning Engineer",
        ),
        judgements=judged(
            ("R1", "direct", ["X1", "X2"]),
            ("R4", "direct", ["K5"]),
            ("R5", "none", []),
        ),
    ),
    GoldenCase(
        name="frontend_supplementary_only",
        profile=profile(
            skills=[
                skill("React"),
                skill("CSS"),
                skill("React", "project", within="Portfolio site"),
                skill("TypeScript", "project", source=SUPP, within="Chrome extension"),
                skill("Jest", "project", source=SUPP, within="Chrome extension"),
            ],
            projects=[
                project("Portfolio site", ["React", "CSS"]),
                project("Chrome extension", ["TypeScript", "Jest"], source=SUPP),
            ],
        ),
        requirements=reqs(
            req("React"),
            req("TypeScript"),
            req("Jest", importance="nice"),
            req("Web accessibility", importance="nice"),
            req("CSS"),
            req("Next.js", importance="nice"),
            title="Frontend Developer Intern",
        ),
        judgements=judged(("R4", "none", []), ("R6", "none", [])),
    ),
    GoldenCase(
        name="devops_career_switcher",
        profile=profile(
            skills=[
                skill("Linux"),
                skill("Bash"),
                skill("Docker", "project", source=SUPP, within="Homelab"),
            ],
            projects=[project("Homelab", ["Docker", "Nginx"], source=SUPP)],
            experience=[
                job("IT Support Associate", "HelpCo", "2023-01", "2024-12", kind="full_time")
            ],
        ),
        requirements=reqs(
            req("Kubernetes"),
            req("Terraform"),
            req("AWS"),
            req("Linux"),
            req("CI/CD"),
            req("Containers"),
            req("1+ years DevOps experience", "experience", min_years=1),
            title="Junior DevOps Engineer",
        ),
        judgements=judged(
            ("R1", "none", []),
            ("R2", "none", []),
            ("R3", "none", []),
            ("R5", "none", []),
            ("R7", "implied", ["X1"]),
        ),
    ),
]
