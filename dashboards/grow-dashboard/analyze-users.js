const { BigQuery } = require('@google-cloud/bigquery');

const bigquery = new BigQuery({
  projectId: 'confluence-point-consulting',
});

async function deepAnalysis() {
  // Get all the potentially "non-active" characteristics
  const query = `
    SELECT
      user_id,
      full_name,
      email,
      usertype_name,
      inactive,
      locked,
      readonly,
      show_on_dashboards,
      archived_at,
      last_activity
    FROM \`confluence-point-consulting.grow.users\`
    WHERE usertype_name IS NULL
    ORDER BY full_name
  `;

  const [nullUsers] = await bigquery.query({ query });
  console.log(`=== USERS WITH NULL USERTYPE (${nullUsers.length} users) ===\n`);
  nullUsers.forEach(u => {
    console.log(`${u.full_name} (${u.email})`);
    console.log(`  inactive: ${u.inactive}, locked: ${u.locked}, readonly: ${u.readonly}`);
    console.log(`  show_on_dashboards: ${u.show_on_dashboards}`);
    console.log(`  last_activity: ${u.last_activity ? u.last_activity.value : 'null'}`);
    console.log('');
  });

  // Check other potential filters
  const filterQuery = `
    SELECT
      'Total users' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`

    UNION ALL

    SELECT
      'Not inactive' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`
    WHERE (inactive IS NULL OR inactive = false)

    UNION ALL

    SELECT
      'Has usertype' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`
    WHERE usertype_name IS NOT NULL
      AND (inactive IS NULL OR inactive = false)

    UNION ALL

    SELECT
      'Show on dashboards = true' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`
    WHERE show_on_dashboards = true
      AND usertype_name IS NOT NULL
      AND (inactive IS NULL OR inactive = false)

    UNION ALL

    SELECT
      'Not readonly' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`
    WHERE (readonly IS NULL OR readonly = false)
      AND show_on_dashboards = true
      AND usertype_name IS NOT NULL
      AND (inactive IS NULL OR inactive = false)

    UNION ALL

    SELECT
      'Not locked' as category,
      COUNT(*) as count
    FROM \`confluence-point-consulting.grow.users\`
    WHERE (locked IS NULL OR locked = false)
      AND (readonly IS NULL OR readonly = false)
      AND show_on_dashboards = true
      AND usertype_name IS NOT NULL
      AND (inactive IS NULL OR inactive = false)

    ORDER BY count DESC
  `;

  const [filters] = await bigquery.query({ query: filterQuery });
  console.log('\n=== PROGRESSIVE FILTERS ===\n');
  filters.forEach(f => console.log(`${f.category}: ${f.count}`));

  // Check if 415 matches any combination
  console.log('\n=== CHECKING FOR 415 ===');
  if (filters.some(f => f.count === 415)) {
    const match = filters.find(f => f.count === 415);
    console.log(`✓ MATCH FOUND: ${match.category} = 415`);
  } else {
    console.log('No exact match to 415 with standard filters');

    // Try excluding null usertype
    const withoutNull = 453 - nullUsers.length;
    console.log(`\nWithout null usertype: ${withoutNull}`);
    console.log(`Difference from 415: ${withoutNull - 415}`);
  }
}

deepAnalysis().catch(console.error);
