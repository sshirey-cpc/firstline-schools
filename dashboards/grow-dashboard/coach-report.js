const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function generateReport() {
  // Get detailed list grouped by school and coach ID
  const query = `
    WITH missing_coaches AS (
      SELECT
        u.full_name as teacher_name,
        s.name as school,
        u.coach_id,
        c.full_name as coach_name
      FROM \`confluence-point-consulting.grow.users\` u
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
      LEFT JOIN \`confluence-point-consulting.grow.users\` c ON u.coach_id = c.user_id
      WHERE u.usertype_name = 'Lead Teacher'
        AND (u.inactive IS NULL OR u.inactive = FALSE)
        AND (u.archived_at IS NULL)
        AND u.coach_id IS NOT NULL
        AND c.full_name IS NULL
    )
    SELECT
      school,
      coach_id,
      STRING_AGG(teacher_name, ', ' ORDER BY teacher_name) as teachers,
      COUNT(*) as teacher_count
    FROM missing_coaches
    GROUP BY school, coach_id
    ORDER BY school, teacher_count DESC
  `;

  const [rows] = await bigquery.query({ query });

  console.log('\n=== TEACHERS WITH MISSING COACH NAMES ===\n');

  let currentSchool = '';
  rows.forEach(row => {
    if (row.school !== currentSchool) {
      currentSchool = row.school;
      console.log(`\n${currentSchool.toUpperCase()}`);
      console.log('='.repeat(60));
    }
    console.log(`\nCoach ID: ${row.coach_id}`);
    console.log(`Teachers (${row.teacher_count}): ${row.teachers}`);
  });

  console.log('\n\n=== AVAILABLE COACHES BY SCHOOL ===\n');

  // Show what coaches ARE available at each school
  const coachesQuery = `
    SELECT DISTINCT
      s.name as school,
      c.full_name as coach_name,
      c.user_id as coach_id,
      COUNT(u.user_id) as current_teacher_count
    FROM \`confluence-point-consulting.grow.users\` u
    JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
    LEFT JOIN \`confluence-point-consulting.grow.users\` c ON u.coach_id = c.user_id
    WHERE u.usertype_name = 'Lead Teacher'
      AND (u.inactive IS NULL OR u.inactive = FALSE)
      AND (u.archived_at IS NULL)
      AND c.full_name IS NOT NULL
    GROUP BY s.name, c.full_name, c.user_id
    ORDER BY s.name, c.full_name
  `;

  const [coaches] = await bigquery.query({ query: coachesQuery });

  let currentSchool2 = '';
  coaches.forEach(row => {
    if (row.school !== currentSchool2) {
      currentSchool2 = row.school;
      console.log(`\n${currentSchool2.toUpperCase()}`);
      console.log('='.repeat(60));
    }
    console.log(`${row.coach_name} (ID: ${row.coach_id}) - ${row.current_teacher_count} teachers`);
  });
}

generateReport().catch(console.error);
