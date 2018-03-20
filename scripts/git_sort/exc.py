#!/usr/bin/python
# -*- coding: utf-8 -*-


class KSException(BaseException):
    pass


class KSError(KSException):
    pass


class KSNotFound(KSError):
    pass
