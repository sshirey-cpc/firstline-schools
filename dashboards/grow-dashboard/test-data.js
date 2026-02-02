const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function testData() {
  // Check users structure
  console.log('=== USERS DATA ===');
  const usersQuery = `
    SELECT
      usertag1,
      usertag2,
      usertag3,
      usertag4,
      default_school_id,
      coach_id,
      full_name,
      usertype_name
    FROM \`confluence-point-consulting.grow.users\`
    WHERE usertype_name = 'Lead Teacher'
      AND (inactive IS NULL OR inactive = FALSE)
      AND archived_at IS NULL
    LIMIT 3
  `;

  const [users] = await bigquery.query({ query: usersQuery });
  console.log(JSON.stringify(users, null, 2));

  // Check assignments
  console.log('\n=== ASSIGNMENTS DATA ===');
  const assignmentsQuery = `
    SELECT
      type,
      COUNT(*) as count,
      MIN(due_date) as earliest,
      MAX(due_date) as latest
    FROM \`confluence-point-consulting.grow.assignments\`
    GROUP BY type
  `;

  const [assignments] = await bigquery.query({ query: assignmentsQuery });
  console.log(JSON.stringify(assignments, null, 2));
}

testData().catch(console.error);
