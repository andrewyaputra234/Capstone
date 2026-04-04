# Rubric Management Guide

## Overview

The Oral Assessment System supports two ways to manage rubrics:
1. **Auto-Generate** - System automatically creates rubrics based on education level
2. **Upload Custom** - Provide your own rubric template in JSON format

---

## Method 1: Auto-Generate Rubrics

### How It Works

The auto-generation feature creates appropriate rubrics based on:
- **Subject Type** (Mathematics, English, Science)
- **Education Level** (Primary, Secondary, High School, University)

### Steps

1. Go to **Upload Document** page
2. Enter your **Subject Name** (e.g., "Math", "Biology", "English Literature")
3. Select **Step 3: Rubric Setup**
4. Choose **"Auto-Generate"** option
5. Select your **Education Level**
6. Click **"🔄 Generate Rubric"**
7. System creates and saves the rubric automatically
8. Upload your document and proceed

### Example Generated Rubrics

**Primary Mathematics:**
- Conceptual Understanding (25 pts)
- Problem Solving (25 pts)
- Calculation Accuracy (25 pts)
- Communication (25 pts)

**High School English:**
- Critical Analysis (20 pts)
- Sophisticated Language Use (20 pts)
- Evidence & Reasoning (20 pts)
- Style & Development (20 pts)
- Conventions & Execution (20 pts)

**University Science:**
- Research Knowledge (20 pts)
- Research Methodology (20 pts)
- Data Analysis & Interpretation (20 pts)
- Scientific Innovation (20 pts)
- Academic Communication (20 pts)

---

## Method 2: Upload Custom Rubric

### How It Works

You can provide your own rubric by uploading a JSON file. This is useful for:
- Custom assessment criteria
- School-specific rubrics
- Subject-specific standards
- Personalized grading scales

### Steps

1. Go to **Upload Document** page
2. Enter your **Subject Name**
3. Select **Step 3: Rubric Setup**
4. Choose **"Upload Custom"** option
5. Click to upload your JSON rubric file
6. System validates and loads your rubric
7. Upload your document and proceed

### Rubric JSON Format

Your custom rubric must follow this JSON structure:

```json
{
  "name": "Your Rubric Name",
  "level": "Custom",
  "subject": "Your Subject",
  "criteria": [
    {
      "name": "Criterion Name",
      "description": "What this criterion measures",
      "max_points": 25,
      "rubric_levels": [
        {
          "level": "Excellent",
          "points": 25,
          "description": "Description of excellent performance"
        },
        {
          "level": "Good",
          "points": 20,
          "description": "Description of good performance"
        },
        {
          "level": "Fair",
          "points": 15,
          "description": "Description of fair performance"
        },
        {
          "level": "Poor",
          "points": 5,
          "description": "Description of poor performance"
        }
      ]
    }
  ]
}
```

### Custom Rubric Example

**Example: Essay Writing Rubric**

```json
{
  "name": "Essay Writing Assessment",
  "level": "Custom",
  "subject": "Writing",
  "criteria": [
    {
      "name": "Thesis & Argument",
      "description": "Clarity and strength of the main argument",
      "max_points": 25,
      "rubric_levels": [
        {
          "level": "Excellent",
          "points": 25,
          "description": "Clear, compelling thesis with strong argument structure"
        },
        {
          "level": "Good",
          "points": 20,
          "description": "Clear thesis with logical argument"
        },
        {
          "level": "Fair",
          "points": 15,
          "description": "Thesis present but somewhat unclear"
        },
        {
          "level": "Poor",
          "points": 5,
          "description": "Weak or missing thesis"
        }
      ]
    },
    {
      "name": "Evidence & Examples",
      "description": "Quality and relevance of supporting evidence",
      "max_points": 25,
      "rubric_levels": [
        {
          "level": "Excellent",
          "points": 25,
          "description": "Strong, relevant evidence throughout"
        },
        {
          "level": "Good",
          "points": 20,
          "description": "Relevant evidence with minor gaps"
        },
        {
          "level": "Fair",
          "points": 15,
          "description": "Some evidence provided"
        },
        {
          "level": "Poor",
          "points": 5,
          "description": "Little or no evidence"
        }
      ]
    },
    {
      "name": "Organization",
      "description": "Structure and flow of ideas",
      "max_points": 25,
      "rubric_levels": [
        {
          "level": "Excellent",
          "points": 25,
          "description": "Excellent structure with smooth transitions"
        },
        {
          "level": "Good",
          "points": 20,
          "description": "Clear organization with good flow"
        },
        {
          "level": "Fair",
          "points": 15,
          "description": "Logical organization with some unclear connections"
        },
        {
          "level": "Poor",
          "points": 5,
          "description": "Disorganized or hard to follow"
        }
      ]
    },
    {
      "name": "Grammar & Style",
      "description": "Correctness and effectiveness of writing",
      "max_points": 25,
      "rubric_levels": [
        {
          "level": "Excellent",
          "points": 25,
          "description": "Excellent grammar with engaging style"
        },
        {
          "level": "Good",
          "points": 20,
          "description": "Good grammar with effective style"
        },
        {
          "level": "Fair",
          "points": 15,
          "description": "Generally correct with minor errors"
        },
        {
          "level": "Poor",
          "points": 5,
          "description": "Frequent errors that impair meaning"
        }
      ]
    }
  ]
}
```

---

## Rubric Template File

A template rubric file is provided at:
```
data/rubrics/RUBRIC_TEMPLATE.json
```

You can:
1. Copy this file
2. Edit it with your custom criteria
3. Save as a new JSON file
4. Upload it to the system

---

## Important Notes

### Auto-Generated Rubrics

- ✅ Subject detection is automatic
- ✅ Points scale with education level
- ✅ Multiple rubric levels (Excellent, Good, Fair, Poor)
- ✅ Saved and reusable
- ⚠️ Cannot be modified through the UI (edit JSON file manually)

### Custom Rubrics

- ✅ Complete control over criteria and points
- ✅ Custom scales and levels
- ✅ Can be reused across documents
- ✅ School/district-specific rubrics supported
- ⚠️ Must be valid JSON format

### Point Scales

- **Primary Level:** 4 criteria × 25 pts = 100 pts total
- **Secondary/High School:** 4-5 criteria × 20-25 pts = 100 pts total
- **University:** 4-5 criteria × 20 pts = 100 pts total

You can adjust points in custom rubrics as needed.

---

## Troubleshooting

### "Invalid JSON File" Error

**Issue:** System says your rubric JSON is invalid
**Solution:** 
- Validate JSON syntax using an online JSON validator
- Ensure all quotes are double quotes (")
- Check that commas are in the right places
- Use the provided template as a reference

### Missing "criteria" Field

**Issue:** "Invalid rubric format. Must have 'criteria' field."
**Solution:**
- Your JSON must include a top-level "criteria" array
- See the format example above

### Auto-Generated Rubric Not Appearing

**Issue:** Generated rubric doesn't show in the dropdown
**Solution:**
- Click "Generate Rubric" button
- Wait for success message
- The rubric will appear in the dropdown
- If not, refresh the page

---

## Switching Between Methods

You can freely switch between auto-generation and custom upload:

1. **First upload (Auto-Generate):** Subject → Education Level → Generate
2. **Second upload (Custom Upload):** Subject → Upload JSON → Process
3. **Third upload (Auto-Generate Again):** Subject → Different Level → Generate

Each method is independent and coexists with the others.

---

## Best Practices

### For Auto-Generated Rubrics

✅ Use for standardized assessments (PSLE, O-Levels, etc.)
✅ Use when you want quick, consistent grading criteria
✅ Use for subjects requiring different rubrics per education level

### For Custom Rubrics

✅ Use for specialized or unique subjects
✅ Use when you have specific learning objectives
✅ Use for school or teacher-specific standards
✅ Use when you need custom point scales

---

## Contact & Support

For questions about rubric format or auto-generation:
- Check the template file: `data/rubrics/RUBRIC_TEMPLATE.json`
- Review examples in `data/rubrics/` directory
- Examine auto-generated rubrics for reference structure
