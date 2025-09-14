# Tenant Settings Deprecation Plan

## Overview
Tenant settings functionality has been migrated from the onboarding service to the OAuth2 Authorization Server. This document outlines the safe removal plan for the old code.

## Migration Status ✅ COMPLETE
- [x] OAuth2 server tenant settings implementation
- [x] Database migration (V6__Add_tenant_settings.sql)
- [x] Proxy controllers for logo operations
- [x] Auto-creation of tenant settings on registration
- [x] Widget service updated to use OAuth2 server
- [x] Fallback mechanisms implemented

## Files Marked for Deletion

### ⚠️ CRITICAL: DO NOT DELETE until Phase 2 validation complete

#### Settings Service Files
```
app/services/settings_service.py          # ❌ Delete after validation
app/models/settings.py                    # ❌ Delete after validation
app/api/settings.py                       # ❌ Delete after validation
```

#### Database Migration Files
```
onboarding_migrations/versions/6edffb133c83_create_tenant_settings_table.py  # ❌ Delete after validation
onboarding_migrations/versions/8c7af17afd5f_add_company_logo_object_name_field.py  # ❌ Delete after validation
```

## Deprecation Timeline

### Phase 1: Migration Complete ✅ DONE
**Duration:** Completed
- Implemented OAuth2 server tenant settings
- Created proxy controllers
- Updated tenant creation process

### Phase 2: Validation & Testing ⏳ CURRENT PHASE
**Duration:** 2-4 weeks  
**Requirements before proceeding to Phase 3:**

1. **✅ Functional Testing:**
   - [ ] Create new tenant → Verify settings created in OAuth2 server
   - [ ] Test all new settings endpoints (GET, PUT, DELETE)
   - [ ] Test all logo proxy endpoints
   - [ ] Verify widget generation uses OAuth2 server
   - [ ] Test fallback mechanisms work when OAuth2 server unavailable

2. **✅ Production Monitoring:**
   - [ ] Monitor tenant creation logs for OAuth2 settings creation
   - [ ] Verify fallback usage is zero or minimal
   - [ ] Check no applications calling old `/api/v1/tenants/{id}/settings` endpoints
   - [ ] Confirm all logo operations go through proxy

3. **✅ Consumer Updates:**
   - [ ] Update any scripts/tools using old endpoints
   - [ ] Update API documentation
   - [ ] Inform stakeholders of new endpoint URLs

### Phase 3: Deprecation Warnings
**Duration:** 2 weeks
**Actions:**
- Return HTTP 410 (Gone) status from old endpoints
- Add deprecation headers to any remaining old endpoints
- Send alerts for any usage of deprecated endpoints

### Phase 4: Safe Deletion
**Duration:** 1 week
**Requirements:**
- ✅ Zero usage of old endpoints for 2+ weeks
- ✅ All functional tests passing
- ✅ Production monitoring shows successful OAuth2 integration
- ✅ Stakeholder approval

**Files to delete:**
```bash
# Settings service implementation
rm app/services/settings_service.py
rm app/models/settings.py
rm app/api/settings.py

# Old database migrations (keep in git history)
rm onboarding_migrations/versions/6edffb133c83_create_tenant_settings_table.py
rm onboarding_migrations/versions/8c7af17afd5f_add_company_logo_object_name_field.py

# Remove from main.py
# Remove: app.include_router(settings_router, prefix=settings.API_V1_STR, tags=["tenant-settings"])
```

## Rollback Plan
If issues are discovered during validation:

1. **Immediate Rollback:**
   - Remove OAuth2 server calls from tenant creation
   - Re-enable local settings creation
   - Update widget service to use local endpoints

2. **Database Rollback:**
   - OAuth2 server data preserved (can revert migration if needed)
   - Onboarding service settings table remains intact

## Success Criteria
- ✅ All new tenant registrations create settings in OAuth2 server
- ✅ Widget generation works with OAuth2 server endpoints
- ✅ Logo operations work through proxy controllers
- ✅ Zero fallback usage to local settings
- ✅ Zero errors in production logs related to settings operations

## Risk Mitigation
- **Gradual rollout:** Fallback mechanisms ensure continuity
- **Monitoring:** Extensive logging to catch issues early
- **Rollback capability:** Old code kept until validation complete
- **Testing:** Comprehensive testing before each phase

## Service-to-Service Authentication
**Note:** Currently using unauthenticated HTTP calls for service communication. 
**TODO:** Implement proper service-to-service authentication before production deployment.

Recommended approaches:
- Service account JWT tokens
- Mutual TLS (mTLS)
- API key authentication
- OAuth2 client credentials flow

## Contact
For questions about this deprecation plan, contact the development team.

---
**Last Updated:** September 9, 2025  
**Next Review:** After Phase 2 validation (2-4 weeks)