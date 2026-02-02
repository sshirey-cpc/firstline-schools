const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function checkUnassigned() {
  // Check which teachers still have missing coach names after refresh
  const query = `
    SELECT
      u.full_name as teacher_name,
      s.name as school,
      u.coach_id,
      c.full_name as coach_name
    FROM \`confluence-point-consulting.grow.users\` u
    LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
    LEFT JOIN (
      SELECT DISTINCT user_id, full_name
      FROM \`confluence-point-consulting.grow.users\`
    ) c ON u.coach_id = c.user_id
    WHERE u.usertype_name = 'Lead Teacher'
      AND (u.inactive IS NULL OR u.inactive = FALSE)
      AND (u.archived_at IS NULL)
      AND u.coach_id IS NOT NULL
      AND c.full_name IS NULL
    ORDER BY s.name, u.full_name
  `;

  const [rows] = await bigquery.query({ query });

  console.log(`\n=== REMAINING UNASSIGNED TEACHERS (${rows.length} total) ===\n`);

  // Group by school and coach ID
  const grouped = {};
  rows.forEach(row => {
    const key = `${row.school}|||${row.coach_id}`;
    if (!grouped[key]) {
      grouped[key] = {
        school: row.school,
        coach_id: row.coach_id,
        teachers: []
      };
    }
    grouped[key].teachers.push(row.teacher_name);
  });

  Object.values(grouped).forEach(group => {
    console.log(`\n${group.school.toUpperCase()}`);
    console.log('='.repeat(60));
    console.log(`Coach ID: ${group.coach_id}`);
    console.log(`Teachers (${group.teachers.length}):`);
    group.teachers.forEach(teacher => console.log(`  - ${teacher}`));
  });

  // Check if Tiffany Willis and Shauntel Butler exist in the system
  console.log('\n\n=== CHECKING FOR TIFFANY WILLIS AND SHAUNTEL BUTLER ===\n');

  const coachQuery = `
    SELECT
      user_id,
      full_name,
      email,
      usertype_name
    FROM \`confluence-point-consulting.grow.users\`
    WHERE full_name LIKE '%Tiffany%Willis%' OR full_name LIKE '%Shauntel%Butler%'
  `;

  const [coaches] = await bigquery.query({ query: coachQuery });
  console.log(JSON.stringify(coaches, null, 2));
}

checkUnassigned().catch(console.error);
