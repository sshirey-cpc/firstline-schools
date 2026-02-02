import { BigQuery } from '@google-cloud/bigquery';

const bigquery = new BigQuery({
  projectId: process.env.BIGQUERY_PROJECT || 'confluence-point-consulting',
  keyFilename: process.env.GOOGLE_APPLICATION_CREDENTIALS,
});

export interface ActionStepStats {
  location: string;
  locationName?: string;
  trimester: 'Trimester 1' | 'Trimester 2';
  totalTeachers: number;
  teachersWith4Steps: number;
  teachersWith2Steps: number;
  teachersWith1Step: number;
  percentWith4Steps: number;
  percentWith2Steps: number;
  percentWith1Step: number;
}

export interface CoachStats extends ActionStepStats {
  coachId: string;
  coachName?: string;
}

export async function getActionStepsByLocation(): Promise<ActionStepStats[]> {
  const query = `
    WITH active_lead_teachers AS (
      SELECT DISTINCT
        u.user_id,
        u.full_name,
        u.default_school_id as location,
        u.coach_id
      FROM \`confluence-point-consulting.grow.users\` u
      WHERE u.usertype_name = 'Lead Teacher'
        AND (u.inactive IS NULL OR u.inactive = FALSE)
        AND (u.archived_at IS NULL)
    ),
    trimester1_steps AS (
      SELECT
        a.user_name,
        COUNT(*) as step_count
      FROM \`confluence-point-consulting.grow.assignments\` a
      WHERE a.type = 'actionStep'
        AND a.created_at <= '2025-11-05'
      GROUP BY a.user_name
    ),
    trimester2_steps AS (
      SELECT
        a.user_name,
        COUNT(*) as step_count
      FROM \`confluence-point-consulting.grow.assignments\` a
      WHERE a.type = 'actionStep'
        AND a.created_at > '2025-11-05'
        AND a.created_at <= CURRENT_TIMESTAMP()
      GROUP BY a.user_name
    ),
    location_stats_t1 AS (
      SELECT
        alt.location,
        s.name as location_name,
        'Trimester 1' as trimester,
        COUNT(DISTINCT alt.user_id) as total_teachers,
        COUNTIF(t1.step_count >= 4) as teachers_with_4_steps,
        COUNTIF(t1.step_count >= 2) as teachers_with_2_steps,
        COUNTIF(t1.step_count >= 1) as teachers_with_1_step
      FROM active_lead_teachers alt
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON alt.location = s.school_id
      LEFT JOIN trimester1_steps t1 ON alt.full_name = t1.user_name
      WHERE alt.location IS NOT NULL
      GROUP BY alt.location, s.name
    ),
    location_stats_t2 AS (
      SELECT
        alt.location,
        s.name as location_name,
        'Trimester 2' as trimester,
        COUNT(DISTINCT alt.user_id) as total_teachers,
        COUNTIF(t2.step_count >= 4) as teachers_with_4_steps,
        COUNTIF(t2.step_count >= 2) as teachers_with_2_steps,
        COUNTIF(t2.step_count >= 1) as teachers_with_1_step
      FROM active_lead_teachers alt
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON alt.location = s.school_id
      LEFT JOIN trimester2_steps t2 ON alt.full_name = t2.user_name
      WHERE alt.location IS NOT NULL
      GROUP BY alt.location, s.name
    )
    SELECT
      COALESCE(location_name, location) as location,
      location_name as locationName,
      trimester,
      total_teachers as totalTeachers,
      teachers_with_4_steps as teachersWith4Steps,
      teachers_with_2_steps as teachersWith2Steps,
      teachers_with_1_step as teachersWith1Step,
      ROUND(SAFE_DIVIDE(teachers_with_4_steps * 100, total_teachers), 1) as percentWith4Steps,
      ROUND(SAFE_DIVIDE(teachers_with_2_steps * 100, total_teachers), 1) as percentWith2Steps,
      ROUND(SAFE_DIVIDE(teachers_with_1_step * 100, total_teachers), 1) as percentWith1Step
    FROM location_stats_t1
    UNION ALL
    SELECT
      COALESCE(location_name, location) as location,
      location_name,
      trimester,
      total_teachers,
      teachers_with_4_steps,
      teachers_with_2_steps,
      teachers_with_1_step,
      ROUND(SAFE_DIVIDE(teachers_with_4_steps * 100, total_teachers), 1) as percentWith4Steps,
      ROUND(SAFE_DIVIDE(teachers_with_2_steps * 100, total_teachers), 1) as percentWith2Steps,
      ROUND(SAFE_DIVIDE(teachers_with_1_step * 100, total_teachers), 1) as percentWith1Step
    FROM location_stats_t2
    ORDER BY location, trimester
  `;

  const [rows] = await bigquery.query({ query });
  return rows as ActionStepStats[];
}

export async function getActionStepsByCoach(): Promise<CoachStats[]> {
  const query = `
    WITH active_lead_teachers AS (
      SELECT DISTINCT
        u.user_id,
        u.full_name,
        u.default_school_id as location,
        u.coach_id
      FROM \`confluence-point-consulting.grow.users\` u
      WHERE u.usertype_name = 'Lead Teacher'
        AND (u.inactive IS NULL OR u.inactive = FALSE)
        AND (u.archived_at IS NULL)
    ),
    coach_info AS (
      SELECT DISTINCT
        user_id,
        full_name
      FROM \`confluence-point-consulting.grow.users\`
    ),
    trimester1_steps AS (
      SELECT
        a.user_name,
        COUNT(*) as step_count
      FROM \`confluence-point-consulting.grow.assignments\` a
      WHERE a.type = 'actionStep'
        AND a.created_at <= '2025-11-05'
      GROUP BY a.user_name
    ),
    trimester2_steps AS (
      SELECT
        a.user_name,
        COUNT(*) as step_count
      FROM \`confluence-point-consulting.grow.assignments\` a
      WHERE a.type = 'actionStep'
        AND a.created_at > '2025-11-05'
        AND a.created_at <= CURRENT_TIMESTAMP()
      GROUP BY a.user_name
    ),
    coach_stats_t1 AS (
      SELECT
        alt.location,
        s.name as location_name,
        alt.coach_id,
        c.full_name as coach_name,
        'Trimester 1' as trimester,
        COUNT(DISTINCT alt.user_id) as total_teachers,
        COUNTIF(t1.step_count >= 4) as teachers_with_4_steps,
        COUNTIF(t1.step_count >= 2) as teachers_with_2_steps,
        COUNTIF(t1.step_count >= 1) as teachers_with_1_step
      FROM active_lead_teachers alt
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON alt.location = s.school_id
      LEFT JOIN coach_info c ON alt.coach_id = c.user_id
      LEFT JOIN trimester1_steps t1 ON alt.full_name = t1.user_name
      WHERE alt.location IS NOT NULL AND alt.coach_id IS NOT NULL
      GROUP BY alt.location, s.name, alt.coach_id, c.full_name
    ),
    coach_stats_t2 AS (
      SELECT
        alt.location,
        s.name as location_name,
        alt.coach_id,
        c.full_name as coach_name,
        'Trimester 2' as trimester,
        COUNT(DISTINCT alt.user_id) as total_teachers,
        COUNTIF(t2.step_count >= 4) as teachers_with_4_steps,
        COUNTIF(t2.step_count >= 2) as teachers_with_2_steps,
        COUNTIF(t2.step_count >= 1) as teachers_with_1_step
      FROM active_lead_teachers alt
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON alt.location = s.school_id
      LEFT JOIN coach_info c ON alt.coach_id = c.user_id
      LEFT JOIN trimester2_steps t2 ON alt.full_name = t2.user_name
      WHERE alt.location IS NOT NULL AND alt.coach_id IS NOT NULL
      GROUP BY alt.location, s.name, alt.coach_id, c.full_name
    )
    SELECT
      COALESCE(location_name, location) as location,
      coach_id as coachId,
      coach_name as coachName,
      trimester,
      total_teachers as totalTeachers,
      teachers_with_4_steps as teachersWith4Steps,
      teachers_with_2_steps as teachersWith2Steps,
      teachers_with_1_step as teachersWith1Step,
      ROUND(SAFE_DIVIDE(teachers_with_4_steps * 100, total_teachers), 1) as percentWith4Steps,
      ROUND(SAFE_DIVIDE(teachers_with_2_steps * 100, total_teachers), 1) as percentWith2Steps,
      ROUND(SAFE_DIVIDE(teachers_with_1_step * 100, total_teachers), 1) as percentWith1Step
    FROM coach_stats_t1
    UNION ALL
    SELECT
      COALESCE(location_name, location) as location,
      coach_id as coachId,
      coach_name as coachName,
      trimester,
      total_teachers,
      teachers_with_4_steps,
      teachers_with_2_steps,
      teachers_with_1_step,
      ROUND(SAFE_DIVIDE(teachers_with_4_steps * 100, total_teachers), 1) as percentWith4Steps,
      ROUND(SAFE_DIVIDE(teachers_with_2_steps * 100, total_teachers), 1) as percentWith2Steps,
      ROUND(SAFE_DIVIDE(teachers_with_1_step * 100, total_teachers), 1) as percentWith1Step
    FROM coach_stats_t2
    ORDER BY location, coachId, trimester
  `;

  const [rows] = await bigquery.query({ query });
  return rows as CoachStats[];
}

export interface GoalStats {
  location: string;
  locationName?: string;
  userType: 'Lead Teacher' | 'Network' | 'School-Based Leader';
  totalUsers: number;
  usersWithGoals: number;
  percentWithGoals: number;
}

export async function getGoalsByUserType(): Promise<GoalStats[]> {
  const query = `
    WITH user_goals AS (
      SELECT DISTINCT user_name
      FROM \`confluence-point-consulting.grow.assignments\`
      WHERE type = 'goal'
    ),
    lead_teachers AS (
      SELECT
        u.default_school_id as location,
        s.name as location_name,
        'Lead Teacher' as user_type,
        COUNT(DISTINCT u.user_id) as total_users,
        COUNT(DISTINCT CASE WHEN g.user_name IS NOT NULL THEN u.user_id END) as users_with_goals
      FROM \`confluence-point-consulting.grow.users\` u
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
      LEFT JOIN user_goals g ON u.full_name = g.user_name
      WHERE u.usertype_name = 'Lead Teacher'
        AND (u.inactive IS NULL OR u.inactive = false)
        AND u.default_school_id IS NOT NULL
      GROUP BY u.default_school_id, s.name
    ),
    network_users AS (
      SELECT
        u.default_school_id as location,
        s.name as location_name,
        'Network' as user_type,
        COUNT(DISTINCT u.user_id) as total_users,
        COUNT(DISTINCT CASE WHEN g.user_name IS NOT NULL THEN u.user_id END) as users_with_goals
      FROM \`confluence-point-consulting.grow.users\` u
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
      LEFT JOIN user_goals g ON u.full_name = g.user_name
      WHERE u.usertype_name = 'Network'
        AND (u.inactive IS NULL OR u.inactive = false)
        AND s.name = 'FLS/Network'
      GROUP BY u.default_school_id, s.name
    ),
    school_leaders AS (
      SELECT
        u.default_school_id as location,
        s.name as location_name,
        'School-Based Leader' as user_type,
        COUNT(DISTINCT u.user_id) as total_users,
        COUNT(DISTINCT CASE WHEN g.user_name IS NOT NULL THEN u.user_id END) as users_with_goals
      FROM \`confluence-point-consulting.grow.users\` u
      LEFT JOIN \`confluence-point-consulting.grow.schools\` s ON u.default_school_id = s.school_id
      LEFT JOIN user_goals g ON u.full_name = g.user_name
      WHERE u.usertype_name = 'School-Based Leader'
        AND (u.inactive IS NULL OR u.inactive = false)
        AND u.default_school_id IS NOT NULL
      GROUP BY u.default_school_id, s.name
    )
    SELECT
      COALESCE(location_name, location) as location,
      location_name as locationName,
      user_type as userType,
      total_users as totalUsers,
      users_with_goals as usersWithGoals,
      ROUND(SAFE_DIVIDE(users_with_goals * 100, total_users), 1) as percentWithGoals
    FROM lead_teachers
    UNION ALL
    SELECT
      COALESCE(location_name, location) as location,
      location_name as locationName,
      user_type as userType,
      total_users as totalUsers,
      users_with_goals as usersWithGoals,
      ROUND(SAFE_DIVIDE(users_with_goals * 100, total_users), 1) as percentWithGoals
    FROM network_users
    UNION ALL
    SELECT
      COALESCE(location_name, location) as location,
      location_name as locationName,
      user_type as userType,
      total_users as totalUsers,
      users_with_goals as usersWithGoals,
      ROUND(SAFE_DIVIDE(users_with_goals * 100, total_users), 1) as percentWithGoals
    FROM school_leaders
    ORDER BY location, userType
  `;

  const [rows] = await bigquery.query({ query });
  return rows as GoalStats[];
}
