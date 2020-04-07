#!/usr/bin/env python

import nengo
import numpy as np

import rospy
from std_msgs.msg import Float64, String

class Base_network():
    def __init__(self, voluntary_joints = [],  rhythmic_joints = [], stim = None, use_stim = True, arm_1_joint_cmd_pos_name = '', arm_2_joint_cmd_pos_name = '', arm_3_joint_cmd_pos_name = ''):
        self.stim = stim
        self.use_stim = use_stim
        self.slider_nr = len(voluntary_joints) + 2* len(rhythmic_joints)
        self.all_motions = voluntary_joints + rhythmic_joints
        self.all_joints =[]
        self.rate = rospy.Rate(10)
        self.error = [0.0, 0.0, 0.0]
        for i in range(len(self.all_motions)):
            for j in range(len(self.all_motions[i])):
                self.all_joints.append(self.all_motions[i][j])
        unique_joints = sorted(set(self.all_joints), key=self.all_joints.index)
        self._joints_pub= [[] for y in range(2)]
        for i in unique_joints:
            self._joints_pub[0].append(i)
            self._joints_pub[1].append(rospy.Publisher(i, Float64, queue_size=1))
        self.result = []
        self.arm_1_joint_cmd_pos_name = arm_1_joint_cmd_pos_name
        self.arm_2_joint_cmd_pos_name = arm_2_joint_cmd_pos_name
        self.arm_3_joint_cmd_pos_name = arm_3_joint_cmd_pos_name
        self.last_duplette = None
        self.last_used_duplette_index = -1
        self.feedback = None
        self.next_pos_delta_factor = rospy.get_param('~next_pos_delta_factor', 1.)
        self.next_pos_error_factor = rospy.get_param('~next_pos_error_factor', 0.33)
        self.arm_3_joint_index = rospy.get_param('~arm_3_joint_index', 3)
        self.max_pos_delta = rospy.get_param('~max_pos_delta', 0.05)
        self.last_publishing_time = rospy.get_rostime()
        self.publishing_time_tolerance = rospy.get_param('~publishing_time_tolerance', 0.1)
        self.base_network_class_data_pub = rospy.Publisher('/base_network_class_data_pub', String, queue_size=1)

    def publish_topic(self, t, x):
        now = rospy.get_rostime()
        from_last_publishing_until_now = now - self.last_publishing_time
        if from_last_publishing_until_now.to_sec() < self.publishing_time_tolerance:
            return
        self.last_publishing_time = now
        if self.use_stim:
            for i in range(len(self._joints_pub[1])):
                self._joints_pub[1][i].publish(x[i])
        else:  # FOR TR(=TARGET REACHING)
            self.to_pub = ''
            for i in range(len(self._joints_pub[1])):
                # NEAR FAR
                if self._joints_pub[0][i] == self.arm_3_joint_cmd_pos_name:
                    if abs(self.error[0]) >= 1:
                        #if self.feedback is None:
                            #self._joints_pub[1][i].publish(x[i])
                        #else:
                            next_pos = self.calculate_next_pos(self.feedback.arm.position[self.arm_3_joint_index - 1], x[i], self.error[0])
                            self.to_pub += 'nf: curr_pos: {}, cmd: {}, next_pos: {}     '.format(self.feedback.arm.position[self.arm_3_joint_index - 1], x[i], next_pos)
                            self._joints_pub[1][i].publish(next_pos)
                # UP DOWN
                elif self._joints_pub[0][i] == self.arm_2_joint_cmd_pos_name:
                    if abs(self.error[1]) >= 1:
                        #if self.feedback is None:
                            #self._joints_pub[1][i].publish(x[i])
                        #else:
                            next_pos = self.calculate_next_pos(self.feedback.arm.position[1], x[i], self.error[1])
                            self.to_pub += 'ud: curr_pos: {}, cmd: {}, next_pos: {}   '.format(self.feedback.arm.position[1], x[i], next_pos)
                            self._joints_pub[1][i].publish(next_pos)
                # LEFT RIGHT
                elif self._joints_pub[0][i] == self.arm_1_joint_cmd_pos_name:
                    if abs(self.error[2]) >= 1:
                        #if self.feedback is None:
                            #self._joints_pub[1][i].publish(x[i])
                        #else:
                            next_pos = self.calculate_next_pos(self.feedback.arm.position[0], x[i], self.error[2])
                            self.to_pub += 'lr: curr_pos: {}, cmd: {}, next_pos: {}     '.format(self.feedback.arm.position[0], x[i], next_pos)
                            self._joints_pub[1][i].publish(next_pos)
            self.base_network_class_data_pub.publish(self.to_pub)

    def calculate_next_pos(self, curr_pos, cmd, curr_error):
        pos_diff = cmd - curr_pos
        delta_sign = np.sign(pos_diff)
        delta_factor = self.next_pos_delta_factor * abs(curr_error) * self.next_pos_error_factor
        delta = delta_sign * min(self.max_pos_delta, abs(delta_factor * pos_diff))
        #next_pos = curr_pos + delta
        next_pos = curr_pos + delta_sign * self.max_pos_delta
        self.to_pub += 'calc: curr_pos: {}, delta_sign: {}, delta_factor: {} cmd: {}, next_pos: {}     '.format(curr_pos, delta_sign, delta_factor, cmd, next_pos)
        return next_pos

    def set_error_near_far(self, x):
        self.error[0] = x[0]
        return x

    def set_error_up_down(self, x):
        self.error[1] = x[0]
        return x

    def set_error_left_right(self, x):
        self.error[2] = x[0]
        return x


    def get_network(self, label):
        net = nengo.Network(label=label)
        with net:
            def blend(x):
                res=[]
                duplette=[]
                tmp=[]
                for i in range(len(x)):
                    # if near_far uses more than 1 joint
                    if self.all_joints[0].count(self.all_joints[i]) == 1:
                        duplette.append([x[i], self.all_joints[i]])
                    else:
                        res.append([x[i], self.all_joints[i]])
                # use only changed value
                if (abs(self.error[1]) >= 1 and abs(self.error[0]) < 1) or (abs(self.error[1]) < 1 and abs(self.error[0]) < 1 and self.last_used_duplette_index == 0):
                    val = duplette[0][0]
                    self.last_used_duplette_index = 0
                elif (abs(self.error[1]) < 1 and abs(self.error[0]) >= 1) or (abs(self.error[1]) < 1 and abs(self.error[0]) < 1 and self.last_used_duplette_index == 1):
                    val = duplette[1][0]
                    self.last_used_duplette_index = 1
                else:
                    val = (duplette[0][0] +  duplette[1][0]) / 2
                    self.last_used_duplette_index = -1
                res.append([val, duplette[0][1]])
                for i in range(len(self._joints_pub[0])):
                    for j in range(len(res)):
                        if self._joints_pub[0][i] == res[j][1]:
                            tmp.append(res[j][0])
                return tmp

            def id_func(x):
                return x

            if self.use_stim:
                if self.stim is None: net.stim = nengo.Node(np.zeros(self.slider_nr))
                else: net.stim = nengo.Node(self.stim, label = 'vol __ a __ b')

            net.f_u= nengo.Ensemble(n_neurons=100, dimensions=len(self.all_joints), radius=2, neuron_type=nengo.Direct(), label ='g(f(u))')   #direct

            if len(self._joints_pub[0]) is not len(self.all_joints):
                net.f_u_blended = nengo.Ensemble(n_neurons=100, dimensions=len(set(self._joints_pub[0])), radius=2, neuron_type=nengo.Direct(), label= 'g(f(u)) blended')    #direct
                nengo.Connection(net.f_u, net.f_u_blended, function= blend, synapse=0.001)
                net.ros_out = nengo.Node(self.publish_topic, size_in=len(self._joints_pub[0]) )
                nengo.Connection(net.f_u_blended, net.ros_out)
            else:
                net.f_u_blended = nengo.Ensemble(n_neurons=100, dimensions=len(set(self._joints_pub[0])), radius=2, neuron_type=nengo.Direct(), label= 'g(f(u)) blended')    #direct
                nengo.Connection(net.f_u, net.f_u_blended, function=id_func, synapse=0.001)
                net.ros_out = nengo.Node(self.publish_topic, size_in=len(self._joints_pub[0]))
                nengo.Connection(net.f_u_blended, net.ros_out)


        return net