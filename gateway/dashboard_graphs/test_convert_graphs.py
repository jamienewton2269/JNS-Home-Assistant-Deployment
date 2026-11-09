import unittest,copy
from convert_graphs import convert,CARD,graph_count
class GraphSemantics(unittest.TestCase):
 def test_daily_and_monthly_change_remain_counter_deltas(self):
  for period,group in [('day','date'),('month','month')]:
   c={'type':'statistics-graph','period':period,'days_to_show':365,'chart_type':'bar','stat_types':['change'],'entities':[{'entity':'sensor.runtime','name':'Hours'}]}
   n,count=convert(c,{})
   self.assertEqual(count,1);self.assertEqual(n['group_by'],group)
   self.assertEqual(n['entities'][0]['aggregate_func'],'change');self.assertEqual(n['hours_to_show'],8760)
 def test_switch_does_not_disappear_from_mixed_history(self):
  c={'type':'history-graph','entities':['sensor.humidity','switch.extractor'],'hours_to_show':24}
  n,_=convert(c,{'sensor.humidity':{'unit':'%'}})
  self.assertEqual(n['entities'][1]['graph_type'],'state_strip')
  self.assertEqual(n['entities'][1]['state_map'][1]['value'],'on')
  self.assertNotIn('value_transform',str(n))
 def test_state_timeline_uses_raw_history(self):
  n,_=convert({'type':'history-graph','entities':['binary_sensor.demand']},{})
  self.assertEqual(n['chart_mode'],'state_timeline');self.assertEqual(n['group_by'],'raw')
 def test_medical_units_do_not_share_one_axis(self):
  n,_=convert({'type':'history-graph','entities':['sensor.hr','sensor.spo2']},{'sensor.hr':{'unit':'bpm'},'sensor.spo2':{'unit':'%'}})
  self.assertEqual([e['graph_group'] for e in n['entities']],['bpm','%'])
 def test_controls_preserved_and_conversion_idempotent(self):
  d={'views':[{'cards':[{'type':'entities','entities':['switch.light']},{'type':'history-graph','entities':['sensor.power']}]}]}
  original=copy.deepcopy(d);n,count=convert(d,{'sensor.power':{'unit':'W'}})
  self.assertEqual(d,original);self.assertEqual(n['views'][0]['cards'][0],d['views'][0]['cards'][0])
  self.assertEqual(convert(n,{})[1],0);self.assertEqual(graph_count(n),1)
 def test_unknown_counter_semantics_fail_before_writes(self):
  with self.assertRaises(ValueError):convert({'type':'statistics-graph','entities':['sensor.energy'],'stat_types':['sum']},{})
if __name__=='__main__':unittest.main()
