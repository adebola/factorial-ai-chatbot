# Document Metadata Enhancement - content_type Field

## Summary

Enhanced the `GET /api/v1/documents/{document_id}/metadata` endpoint to include `content_type` information from the vector database, providing parity with the website ingestion status endpoint.

## Problem Solved

### Before Enhancement
The metadata endpoint returned comprehensive categorization (categories, tags) but was **missing** the `content_type` field that indicates how the AI classified the document content.

**Missing Information**:
```json
{
  "document_id": "...",
  "categories": [...],
  "tags": [...],
  "categorization_summary": {
    "total_categories": 2,
    "total_tags": 3
  }
  // ❌ NO content_type information
}
```

### After Enhancement
The endpoint now includes:
- **Primary content_type** - Most common classification across all chunks
- **Content types distribution** - Breakdown of all content types found
- **Categorization flags** - Indicators showing if content_type data exists

**Complete Information**:
```json
{
  "document_id": "...",
  "content_type": "report",
  "content_types_distribution": {
    "report": 30,
    "contract": 20,
    "other": 4
  },
  "categories": [...],
  "tags": [...],
  "categorization_summary": {
    "total_categories": 2,
    "total_tags": 3,
    "has_content_type": true,
    "content_type_chunks": 54
  }
}
```

## Implementation Details

### File Modified
**`app/api/documents.py`** - Lines 496-570

### Changes Made

#### 1. Added Content Type Distribution Query

```python
# Get content type distribution from vector database
content_types = vector_db.execute(
    text("""
        SELECT content_type, COUNT(*) as count
        FROM vectors.document_chunks
        WHERE document_id = :document_id AND content_type IS NOT NULL
        GROUP BY content_type
        ORDER BY count DESC
    """),
    {"document_id": document_id}
).fetchall()

# Get primary content type (most common)
primary_content_type = content_types[0].content_type if content_types else None

# Build content types distribution
content_types_distribution = {
    ct.content_type: ct.count
    for ct in content_types
} if content_types else {}
```

#### 2. Added to Response Structure

```python
return {
    # ... existing fields ...
    "content_type": primary_content_type,              # NEW
    "content_types_distribution": content_types_distribution,  # NEW
    # ... existing fields ...
    "categorization_summary": {
        # ... existing summary ...
        "has_content_type": primary_content_type is not None,  # NEW
        "content_type_chunks": sum(content_types_distribution.values()) if content_types_distribution else 0  # NEW
    }
}
```

## API Response Examples

### Example 1: Document with Multiple Content Types

**Request**:
```bash
GET /api/v1/documents/8875c946-cf31-4493-8d37-938faff5ef25/metadata
Authorization: Bearer {token}
```

**Response** (if document was processed with new code):
```json
{
  "document_id": "8875c946-cf31-4493-8d37-938faff5ef25",
  "filename": "annual-report-2024.pdf",
  "file_size": 2048576,
  "mime_type": "application/pdf",
  "status": "completed",
  "content_type": "report",
  "content_types_distribution": {
    "report": 30,
    "contract": 15,
    "presentation": 9
  },
  "categories": [
    {
      "id": "cat-1",
      "name": "Financial",
      "confidence_score": 0.95
    }
  ],
  "tags": [
    {
      "id": "tag-1",
      "name": "annual report",
      "tag_type": "auto"
    }
  ],
  "processing_stats": {
    "chunk_count": 54,
    "has_vector_data": true
  },
  "categorization_summary": {
    "total_categories": 1,
    "total_tags": 3,
    "ai_assigned_categories": 1,
    "user_assigned_categories": 0,
    "auto_tags": 3,
    "custom_tags": 0,
    "has_content_type": true,
    "content_type_chunks": 54
  }
}
```

### Example 2: Document Without Content Type (Old Upload)

**Request**:
```bash
GET /api/v1/documents/old-document-id/metadata
```

**Response** (document uploaded before fix):
```json
{
  "document_id": "old-document-id",
  "filename": "old-file.pdf",
  "content_type": null,
  "content_types_distribution": {},
  "categories": [...],
  "tags": [...],
  "categorization_summary": {
    "total_categories": 2,
    "total_tags": 5,
    "has_content_type": false,
    "content_type_chunks": 0
  }
}
```

### Example 3: Single Content Type

**Response**:
```json
{
  "content_type": "contract",
  "content_types_distribution": {
    "contract": 42
  },
  "categorization_summary": {
    "has_content_type": true,
    "content_type_chunks": 42
  }
}
```

## Field Descriptions

### Top-Level Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `content_type` | string \| null | Primary (most common) content type across all chunks | `"report"` |
| `content_types_distribution` | object | Count of chunks per content type | `{"report": 30, "contract": 20}` |

### Categorization Summary Fields

| Field | Type | Description |
|-------|------|-------------|
| `has_content_type` | boolean | Whether any chunks have content_type data |
| `content_type_chunks` | integer | Total number of chunks with content_type populated |

## Content Type Values

Based on AI classification, documents can have these content types:

| Content Type | Description | Examples |
|-------------|-------------|----------|
| `contract` | Legal agreements, terms | Employment contracts, NDAs, vendor agreements |
| `invoice` | Billing documents | Sales invoices, purchase orders, receipts |
| `report` | Analytical documents | Financial reports, quarterly reviews, status reports |
| `email` | Email correspondence | Email threads, newsletters |
| `presentation` | Slide decks | PowerPoint content, pitch decks |
| `manual` | User guides | Product manuals, how-to guides, technical docs |
| `policy` | Rules, procedures | Company policies, HR policies, compliance docs |
| `specification` | Technical specs | Product specs, technical requirements, API docs |
| `other` | Miscellaneous | Content that doesn't fit above categories |

## Use Cases

### 1. UI Display
```javascript
// Show document type icon based on content_type
const getDocumentIcon = (contentType) => {
  const icons = {
    'contract': '📄',
    'invoice': '💰',
    'report': '📊',
    'email': '📧',
    'presentation': '📽️',
    'manual': '📚',
    'policy': '📋',
    'specification': '🔧',
    'other': '📁'
  };
  return icons[contentType] || icons['other'];
};
```

### 2. Filtering
```javascript
// Filter documents by content type
const contractDocs = documents.filter(doc =>
  doc.content_type === 'contract'
);
```

### 3. Analytics
```javascript
// Analyze document type distribution
const typeDistribution = documents.reduce((acc, doc) => {
  const type = doc.content_type || 'unknown';
  acc[type] = (acc[type] || 0) + 1;
  return acc;
}, {});
```

### 4. Search Enhancement
```javascript
// Search only within specific document types
const searchReports = async (query) => {
  const results = await search(query, {
    filters: { content_type: 'report' }
  });
};
```

## Comparison with Website Ingestion Endpoint

Both endpoints now return similar categorization structure:

| Feature | Documents `/metadata` | Websites `/status` | Status |
|---------|----------------------|-------------------|--------|
| **content_type** | ✅ Primary type | ✅ Primary type | Consistent |
| **content_types_distribution** | ✅ All types | ✅ All types | Consistent |
| **categories** | ✅ With details | ✅ With names/IDs | Consistent |
| **tags** | ✅ With details | ✅ With names/IDs | Consistent |
| **categorization_summary** | ✅ Stats | ✅ Stats | Consistent |

## Benefits

### 1. Feature Parity
- Documents and website ingestions now have consistent metadata structure
- Same categorization information available for both content types

### 2. Enhanced User Experience
- Users can see how AI classified their documents
- UI can display appropriate icons/badges based on content type
- Better filtering and search capabilities

### 3. Transparency
- Shows distribution when document contains mixed content types
- Indicates which chunks have categorization data
- Helps identify documents that need re-processing

### 4. Future-Proof
- Ready for content-type-based filtering in chat service
- Supports advanced search features
- Enables analytics and reporting

## Backward Compatibility

✅ **Fully backward compatible**

- **New fields added** - No existing fields removed or changed
- **Null-safe** - Returns `null` for content_type if not available
- **Empty objects** - Returns `{}` for content_types_distribution if none
- **Boolean flags** - `has_content_type` indicates data availability
- **Old clients** - Ignore new fields, continue working normally
- **New clients** - Benefit from enhanced information

## Testing

### Test with Existing Document (No content_type)

```bash
# Get metadata for old document
curl http://localhost:8001/api/v1/documents/8875c946-cf31-4493-8d37-938faff5ef25/metadata \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.content_type, .content_types_distribution, .categorization_summary.has_content_type'

# Expected output:
# null
# {}
# false
```

### Test with New Document Upload

```bash
# 1. Upload new document with categorization
curl -X POST http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-report.pdf" \
  -F "auto_categorize=true"

# Response includes document_id

# 2. Get metadata
curl http://localhost:8001/api/v1/documents/{new-document-id}/metadata \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.content_type, .content_types_distribution'

# Expected output:
# "report"
# {
#   "report": 35,
#   "other": 5
# }
```

### Verify Database

```sql
-- Check content_type in vector database
SELECT content_type, COUNT(*) as count
FROM vectors.document_chunks
WHERE document_id = 'your-document-id'
  AND content_type IS NOT NULL
GROUP BY content_type
ORDER BY count DESC;
```

## Migration Notes

### Existing Documents

Documents uploaded **before** the vector ingestion fix will have:
- `content_type: null`
- `content_types_distribution: {}`
- `has_content_type: false`

This is expected and does not require action.

### Re-processing Old Documents

If you want content_type for old documents:

**Option 1: Re-upload**
1. Delete old document via API
2. Re-upload with `auto_categorize=true`
3. New version will have content_type

**Option 2: Accept as-is**
- Old documents searchable but not filterable by content_type
- New uploads automatically get content_type
- Gradual migration as users replace old documents

## Related Enhancements

This enhancement complements:
1. **Website Ingestion Categorization** - Similar metadata structure
2. **Chat Service Intent Detection** - Uses content_type for smart filtering
3. **Vector Search Enhancement** - Supports content_type filtering

## Summary

✅ **Enhanced** - Document metadata endpoint now includes content_type
✅ **Consistent** - Matches website ingestion response structure
✅ **Informative** - Shows distribution and statistics
✅ **Compatible** - No breaking changes to existing API
✅ **Complete** - Provides full categorization picture

Users now have complete visibility into how their documents are classified, enabling better organization, search, and analytics.
