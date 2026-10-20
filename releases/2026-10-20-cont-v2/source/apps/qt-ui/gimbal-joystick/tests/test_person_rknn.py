"""Pinned vendor-logit decoder checks; no runtime needed."""
import sys
import unittest
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from person_rknn import ANCHORS,decode_head,nms,Attr

class DecodeTest(unittest.TestCase):
    def setUp(self):
        self.attr=Attr(index=0,scale=.1,zp=0)
        self.q=np.zeros((3,85,80,80),np.int8)
    def test_logits_and_coordinate_mapping(self):
        self.q[0,4:6,10,20]=100
        boxes=decode_head(self.q.reshape(255,80,80),self.attr,ANCHORS[0])
        self.assertEqual(len(boxes),1)
        box=boxes[0]
        self.assertAlmostEqual((box['left']+box['right'])/2,20.5/80)
        self.assertAlmostEqual((box['top']+box['bottom'])/2,10.5/80)
        self.assertAlmostEqual(box['right']-box['left'],10/640)
        self.assertAlmostEqual(box['bottom']-box['top'],13/640)
        self.assertGreater(box['score'],.99)
    def test_background_and_other_class_are_not_people(self):
        self.assertEqual(decode_head(self.q.reshape(255,80,80),self.attr,ANCHORS[0]),[])
        self.q[0,4:6,10,20]=100
        self.q[0,7,10,20]=110
        self.assertEqual(decode_head(self.q.reshape(255,80,80),self.attr,ANCHORS[0]),[])
    def test_real_head_zero_point_is_applied(self):
        self.attr.zp=83
        self.attr.scale=.09313568472862244
        self.q.fill(83)
        self.q[0,4:6,10,20]=127
        boxes=decode_head(self.q.reshape(255,80,80),self.attr,ANCHORS[0])
        self.assertEqual(len(boxes),1)
        self.assertAlmostEqual((boxes[0]['left']+boxes[0]['right'])/2,20.5/80)
        self.assertGreater(boxes[0]['score'],.96)
    def test_shape_and_quantization_are_checked(self):
        with self.assertRaises(ValueError):
            decode_head(self.q,self.attr,ANCHORS[0])
        self.attr.scale=0
        with self.assertRaises(ValueError):
            decode_head(self.q.reshape(255,80,80),self.attr,ANCHORS[0])
    def test_nms_keeps_separate_people_and_strongest_duplicate(self):
        person=dict(left=.1,top=.1,right=.3,bottom=.8,score=.8)
        duplicate=dict(person,left=.11,score=.6)
        other=dict(person,left=.7,right=.9,score=.7)
        self.assertEqual(nms([duplicate,other,person]),[person,other])

if __name__=='__main__':unittest.main()
