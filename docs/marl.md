# Multi Agent Reinforcement Learning

## Table of Contents

- [Multi Agent Reinforcement Learning](#multi-agent-reinforcement-learning)
  - [Table of Contents](#table-of-contents)
  - [SARL to MARL](#sarl-to-marl)
    - [Pettingzoo as a MARL gym environment](#pettingzoo-as-a-marl-gym-environment)
  - [Open Tasks](#open-tasks)
    - [Multi Process Parallelization](#multi-process-parallelization)
    - [Multi Agent Scenario Evaluations](#multi-agent-scenario-evaluations)
    - [Multi PPO Training with different NN and Robot Models](#multi-ppo-training-with-different-nn-and-robot-models)
  - [Sources and Additional information](#sources-and-additional-information)

## SARL to MARL

Many of the recent breakthroughs in the reinforcement learning community deal with the problem of having a computational agent act in a simulated or real environment reacting dynamically to new situation. Think of DeepMind's QLearning algorithm playing classic Atari games or AlphaGo beating Lee Sedol in one of the most complicated games in human history. Many more examples can be listed here, but all of them have one thing in common - they always deal with only one agent at a time. This assumption not always holds true in our increasingly connected world. Computational agents often interact with eachother - be it as traders in a common stock exchanges or as service robots navigating thorugh the same area. In order to predict potential dynamics and prepare agents for better real world deployments, it is therefore crucial to be able to simulate MARL environments efficiently.

### Pettingzoo as a MARL gym environment

One of the de-facto standard libraries in the reinforcement learning community is OpenAI gym. This library defines a concrete interface for interaction between simulated environment and agents.

Pettingzoo on the other hand extends the ideas from OpenAI gym to MARL problems. Furthermore it aims to be compatible with existing collections of RL algorithms like stable-baselines3 (SB3).

Pettingzoo achieves this by mostly following the design decisions of OpenAI gym. The main differences are that observation and action spaces are not attributes of an environment anymore, but are inherent to each agent. This allows that heterogeneous agents are able to interact in one environment.

In order to be compatible with existing APIs which are mainly designed for SARL Pettingzoo applies several steps.

At the beginning stands the MARL environment. Pettingzoo offers two different API designs at this point. The first option is to model ones environment as a Agent Environment Cycle (AEC). This idiom was introduced by Terry et. al. [1] in 2020 and describes the MARL problem as a sequential and turn-based game. Each agent observes the current environment, computes an action and executes that action. Only then, the next agent starts his turn and observes the new state of the environment in turn. Terry et. al. argue that this structure improves the predictability of the environment by more closely resembling the implementational details. Many real situations and setups can be approximated using this idiom, but there are just as many situations where a strictly sequential ordering of the agents may not represent the underlying situation accuratly enough. Cooperative navigation is one such example since service robots can not rely on a global ordering of actions. Therefore Pettingzoo offers a second API for MARL. The Parallel API allows agents to observe, compute actions and act - all at the same time. Since it models cooperative navigation better, we chose the Parallel API for implementation in arena-rosnav.

Once you implemented your environment in Pettingzoo and tested it using the appropriate environment tests for compliance with the API, the next step is creating a connection to SB3. For this purpose Pettingzoo created a separate library of useful wrappers called Supersuit. The notion of a wrapper is the same as in OpenAI gym. These functions wrap an environment and modify input or output of that environment while still retaining the API. This makes it possible to mix and match different wrappers in order to customize your environment. Using the existing Supersuit wrappers enables the usage of SB3 models out-of-the-box. For an example hot to achieve this, please refer to the code [here](arena_navigation/arena_local_planner/learning_based/arena_local_planner_drl/scripts/training/train_marl_agent.py)

###

## Open Tasks

### Multi Process Parallelization

### Multi Agent Scenario Evaluations

### Multi PPO Training with different NN and Robot Models

## Sources and Additional information

[1] https://arxiv.org/abs/2009.13051

[Environment documentation] https://ignc-research.github.io/arena-marl/arena_local_planner_drl/rl_agent/

[Scripts documentation] https://ignc-research.github.io/arena-marl/arena_local_planner_drl/scripts/
