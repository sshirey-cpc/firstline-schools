'use client';

import { useState, useEffect } from 'react';
import Header from '@/components/Header';
import ActionStepsTable from '@/components/ActionStepsTable';
import GoalsTable from '@/components/GoalsTable';
import { ActionStepStats, CoachStats, GoalStats } from '@/lib/bigquery';

export default function Home() {
  const [viewType, setViewType] = useState<'location' | 'coach' | 'goals'>('location');
  const [data, setData] = useState<ActionStepStats[] | CoachStats[] | GoalStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/data?view=${viewType}`);
      if (!response.ok) {
        throw new Error('Failed to fetch data');
      }
      const result = await response.json();
      setData(result);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [viewType]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50/30 to-orange-50/20">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
        {/* View Toggle and Controls */}
        <div className="mb-8 flex items-center justify-between bg-white rounded-xl shadow-md p-4">
          <div className="inline-flex rounded-lg border-2 border-fls-navy/20 bg-gray-50 p-1.5 shadow-inner">
            <button
              onClick={() => setViewType('location')}
              className={`px-6 py-2.5 rounded-md text-sm font-semibold transition-all duration-200 ${
                viewType === 'location'
                  ? 'bg-gradient-to-r from-fls-orange to-orange-600 text-white shadow-lg transform scale-105'
                  : 'text-gray-700 hover:bg-white hover:shadow-sm'
              }`}
            >
              Action Steps
            </button>
            <button
              onClick={() => setViewType('coach')}
              className={`px-6 py-2.5 rounded-md text-sm font-semibold transition-all duration-200 ${
                viewType === 'coach'
                  ? 'bg-gradient-to-r from-fls-orange to-orange-600 text-white shadow-lg transform scale-105'
                  : 'text-gray-700 hover:bg-white hover:shadow-sm'
              }`}
            >
              By Coach
            </button>
            <button
              onClick={() => setViewType('goals')}
              className={`px-6 py-2.5 rounded-md text-sm font-semibold transition-all duration-200 ${
                viewType === 'goals'
                  ? 'bg-gradient-to-r from-fls-orange to-orange-600 text-white shadow-lg transform scale-105'
                  : 'text-gray-700 hover:bg-white hover:shadow-sm'
              }`}
            >
              Goals
            </button>
          </div>

          <div className="flex items-center gap-4">
            {lastUpdated && (
              <span className="text-sm text-gray-600 font-medium">
                Last updated: {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={fetchData}
              disabled={loading}
              className="px-6 py-2.5 bg-gradient-to-r from-fls-blue to-blue-600 text-white rounded-lg text-sm font-semibold hover:shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed transform hover:scale-105"
            >
              {loading ? 'Refreshing...' : 'Refresh Data'}
            </button>
          </div>
        </div>

        {/* Info Card */}
        <div className="mb-8 bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-200/50 rounded-xl shadow-md p-6">
          <h3 className="text-base font-bold text-fls-navy mb-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-fls-blue" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            Dashboard Information
          </h3>
          {viewType === 'goals' ? (
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Shows percent of users with <strong>goals</strong> by location</li>
              <li>• <strong>Lead Teachers:</strong> Grouped by school location</li>
              <li>• <strong>Network:</strong> Only users at FLS/Network location</li>
              <li>• <strong>School-Based Leaders:</strong> Grouped by school location</li>
              <li>• Includes only <strong>active users</strong></li>
              <li>• Data updates automatically when the Grow pipeline runs</li>
            </ul>
          ) : (
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• <strong>Trimester 1:</strong> Action steps through November 5th, 2025</li>
              <li>• <strong>Trimester 2:</strong> Action steps from November 6th through current date</li>
              <li>• Includes only <strong>active Lead Teachers</strong></li>
              <li>• Data updates automatically when the Grow pipeline runs</li>
            </ul>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-fls-orange border-t-transparent rounded-full animate-spin"></div>
              <p className="text-gray-600">Loading data from BigQuery...</p>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6">
            <h3 className="text-red-900 font-semibold mb-2">Error loading data</h3>
            <p className="text-red-700">{error}</p>
            <button
              onClick={fetchData}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        )}

        {/* Data Table */}
        {!loading && !error && data.length > 0 && (
          <>
            {viewType === 'goals' ? (
              <GoalsTable data={data as GoalStats[]} />
            ) : (
              <ActionStepsTable data={data as ActionStepStats[] | CoachStats[]} viewType={viewType} />
            )}
          </>
        )}

        {/* No Data State */}
        {!loading && !error && data.length === 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
            <p className="text-yellow-800">No data available. Please check your BigQuery connection.</p>
          </div>
        )}
      </main>
    </div>
  );
}
