'use client';

import { GoalStats } from '@/lib/bigquery';

interface GoalsTableProps {
  data: GoalStats[];
}

export default function GoalsTable({ data }: GoalsTableProps) {
  // Group data by location
  const groupedData = data.reduce((acc, item) => {
    const key = item.location;
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {} as Record<string, GoalStats[]>);

  return (
    <div className="space-y-8">
      {Object.entries(groupedData).map(([location, items]) => (
        <div key={location} className="bg-white rounded-xl shadow-xl overflow-hidden border border-gray-100 hover:shadow-2xl transition-shadow duration-300">
          <div className="bg-gradient-to-r from-fls-navy to-fls-blue text-white px-6 py-5">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
              </svg>
              {location}
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                    User Type
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                    Total Users
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                    Users with Goals
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                    Percent with Goals
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {items.map((item, idx) => (
                  <tr key={idx} className="hover:bg-blue-50/30 transition-colors duration-150">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900">
                      {item.userType}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {item.totalUsers}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {item.usersWithGoals}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className="px-4 py-2 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-base shadow-lg">
                        {item.percentWithGoals}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
