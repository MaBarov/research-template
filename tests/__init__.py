"""Test packages live under real packages so module names stay unique.

Without this file pytest treats ``tests/framework/`` as the import root and binds
the top-level name ``framework`` to the test package, shadowing the production
package it is meant to exercise.
"""
