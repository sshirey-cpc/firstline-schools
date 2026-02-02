import { NextResponse } from 'next/server';
import { getActionStepsByLocation, getActionStepsByCoach, getGoalsByUserType } from '@/lib/bigquery';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const view = searchParams.get('view') || 'location';

    if (view === 'coach') {
      const data = await getActionStepsByCoach();
      return NextResponse.json(data);
    } else if (view === 'goals') {
      const data = await getGoalsByUserType();
      return NextResponse.json(data);
    } else {
      const data = await getActionStepsByLocation();
      return NextResponse.json(data);
    }
  } catch (error) {
    console.error('Error fetching data:', error);
    return NextResponse.json(
      { error: 'Failed to fetch data from BigQuery' },
      { status: 500 }
    );
  }
}

export const dynamic = 'force-dynamic';
export const revalidate = 0;
