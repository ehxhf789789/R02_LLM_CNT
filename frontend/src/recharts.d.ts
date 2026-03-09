// Suppress recharts + React 18 type errors
// This is a known issue: https://github.com/recharts/recharts/issues/3615
declare module 'recharts' {
  export const BarChart: any;
  export const Bar: any;
  export const XAxis: any;
  export const YAxis: any;
  export const CartesianGrid: any;
  export const Tooltip: any;
  export const Legend: any;
  export const RadarChart: any;
  export const PolarGrid: any;
  export const PolarAngleAxis: any;
  export const PolarRadiusAxis: any;
  export const Radar: any;
  export const LineChart: any;
  export const Line: any;
  export const ResponsiveContainer: any;
  export const PieChart: any;
  export const Pie: any;
  export const Cell: any;
  export const ScatterChart: any;
  export const Scatter: any;
  export const ZAxis: any;
  export const Treemap: any;
}
