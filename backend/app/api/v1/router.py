from fastapi import APIRouter

from app.api.v1 import auth, business, enrollment, programs, scan

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(business.router, prefix="/business", tags=["business"])
router.include_router(programs.router, prefix="/programs", tags=["programs"])
router.include_router(scan.router, prefix="/scan", tags=["scan"])
router.include_router(enrollment.router, tags=["enrollment"])
