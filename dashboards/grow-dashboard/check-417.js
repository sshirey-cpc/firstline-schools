const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function checkExtras() {
  // Check for test/practice accounts
  const query = `
    SELECT
      user_id,
      full_name,
      email,
      usertype_name,
      inactive,
      show_on_dashboards
    FROM \`confluence-point-consulting.grow.users\`
    WHERE usertype_name IS NULL
       OR email LIKE '%practice%'
       OR email LIKE '%sample%'
    ORDER BY full_name
  `;

  const [rows] = await bigquery.query({ query });
  console.log(`Potential test/null usertype accounts (${rows.length} total):\n`);
  rows.forEach(r => {
    console.log(`  ${r.full_name} (${r.email})`);
    console.log(`    usertype: ${r.usertype_name}, inactive: ${r.inactive}, show_on_dashboards: ${r.show_on_dashboards}`);
  });

  // Get detailed counts
  const countQuery = `
    SELECT
      COUNT(*) as total,
      COUNT(CASE WHEN inactive = true THEN 1 END) as inactive_true,
      COUNT(CASE WHEN usertype_name IS NULL THEN 1 END) as null_usertype,
      COUNT(CASE WHEN usertype_name IS NOT NULL AND (inactive IS NULL OR inactive = false) THEN 1 END) as active_with_usertype
    FROM \`confluence-point-consulting.grow.users\`
  `;

  const [counts] = await bigquery.query({ query: countQuery });
  console.log('\n\nBreakdown:');
  console.log(`Total users: ${counts[0].total}`);
  console.log(`Inactive=true: ${counts[0].inactive_true}`);
  console.log(`Null usertype: ${counts[0].null_usertype}`);
  console.log(`Active with usertype: ${counts[0].active_with_usertype}`);

  const diff = counts[0].total - 415;
  console.log(`\nDifference from 415: ${diff} extra users`);
}

checkExtras().catch(console.error);
