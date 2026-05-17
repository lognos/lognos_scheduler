# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Added P6-style schedule view modes for longest-path critical path, total-float critical, near-critical, and Float Path 1 analysis.
- Added config-aware schedule view snapshot invalidation so cached views rebuild when critical-path semantics change.

### Changed

- Changed the system Critical Path view to use longest-path semantics instead of only filtering activities with total float less than or equal to zero.