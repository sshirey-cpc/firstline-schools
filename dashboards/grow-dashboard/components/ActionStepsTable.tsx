'use client';

import { ActionStepStats, CoachStats } from '@/lib/bigquery';

interface ActionStepsTableProps {
  data: ActionStepStats[] | CoachStats[];
  viewType: 'location' | 'coach';
}

export default function ActionStepsTable({ data, viewType }: ActionStepsTableProps) {
  // Group data by location
  const groupedData = data.reduce((acc, item) => {
    const key = item.location;
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {} as Record<string, (ActionStepStats | CoachStats)[]>);

  return (
    <div className="space-y-8">
      {Object.entries(groupedData).map(([location, items]) => {
        const isCoachView = viewType === 'coach';
        const coachItems = items as CoachStats[];

        // Group by coach if in coach view
        const coachGroups = isCoachView
          ? coachItems.reduce((acc, item) => {
              const key = item.coachId || 'unassigned';
              if (!acc[key]) {
                acc[key] = { name: item.coachName || 'Unassigned', data: [] };
              }
              acc[key].data.push(item);
              return acc;
            }, {} as Record<string, { name: string; data: CoachStats[] }>)
          : null;

        return (
          <div key={location} className="bg-white rounded-xl shadow-xl overflow-hidden border border-gray-100 hover:shadow-2xl transition-shadow duration-300">
            <div className="bg-gradient-to-r from-fls-navy to-fls-blue text-white px-6 py-5">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                </svg>
                {location}
              </h2>
            </div>

            {!isCoachView ? (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                        Trimester
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                        Total Teachers
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                        4+ Action Steps
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                        2+ Action Steps
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                        1+ Action Steps
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {items.map((item, idx) => (
                      <tr key={idx} className="hover:bg-blue-50/30 transition-colors duration-150">
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900">
                          {item.trimester}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                          {item.totalTeachers}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <div className="flex items-center gap-3">
                            <span className="text-gray-900 font-medium">
                              {item.teachersWith4Steps}
                            </span>
                            <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                              {item.percentWith4Steps}%
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <div className="flex items-center gap-3">
                            <span className="text-gray-900 font-medium">
                              {item.teachersWith2Steps}
                            </span>
                            <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                              {item.percentWith2Steps}%
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <div className="flex items-center gap-3">
                            <span className="text-gray-900 font-medium">
                              {item.teachersWith1Step}
                            </span>
                            <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                              {item.percentWith1Step}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {coachGroups && Object.entries(coachGroups).map(([coachId, coachGroup]) => (
                  <div key={coachId} className="p-6 bg-gradient-to-r from-white to-blue-50/20">
                    <h3 className="text-lg font-bold text-fls-blue mb-4 flex items-center gap-2">
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
                      </svg>
                      {coachGroup.name}
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                          <tr>
                            <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                              Trimester
                            </th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                              Total Teachers
                            </th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                              4+ Action Steps
                            </th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                              2+ Action Steps
                            </th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-fls-navy uppercase tracking-wider">
                              1+ Action Steps
                            </th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {coachGroup.data.map((item, idx) => (
                            <tr key={idx} className="hover:bg-blue-50/30 transition-colors duration-150">
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900">
                                {item.trimester}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                {item.totalTeachers}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm">
                                <div className="flex items-center gap-3">
                                  <span className="text-gray-900 font-medium">
                                    {item.teachersWith4Steps}
                                  </span>
                                  <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                                    {item.percentWith4Steps}%
                                  </span>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm">
                                <div className="flex items-center gap-3">
                                  <span className="text-gray-900 font-medium">
                                    {item.teachersWith2Steps}
                                  </span>
                                  <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                                    {item.percentWith2Steps}%
                                  </span>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm">
                                <div className="flex items-center gap-3">
                                  <span className="text-gray-900 font-medium">
                                    {item.teachersWith1Step}
                                  </span>
                                  <span className="px-3 py-1 bg-gradient-to-r from-fls-orange to-orange-600 text-white font-bold rounded-full text-xs shadow-sm">
                                    {item.percentWith1Step}%
                                  </span>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
