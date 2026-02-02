const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function testAssignments() {
  console.log('=== ACTION STEPS WITH DATES ===');
  const query = `
    SELECT
      id,
      title,
      due_date,
      created_at,
      user_name
    FROM \`confluence-point-consulting.grow.assignments\`
    WHERE type = 'actionStep'
    LIMIT 10
  `;

  const [assignments] = await bigquery.query({ query });
  console.log(JSON.stringify(assignments, null, 2));
}

testAssignments().catch(console.error);
